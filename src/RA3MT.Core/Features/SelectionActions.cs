using RA3MT.Core.Memory;
using RA3MT.Core.Model;

namespace RA3MT.Core.Features;

/// <summary>One-shot actions on the game's selected drawable linked list.</summary>
public static class SelectionActions
{
    public static int Apply(IInjectionMemory mem, FeaturesData data, string version,
        string action, nuint imageBase, SelectionActionState? state = null)
    {
        if (action == "oreminerestore")
            return RestoreOreMines(mem, data, version, imageBase);
        if (action == "capture")
            throw new NotSupportedException("俘虏需要游戏归属切换流程，不能直接覆盖属主指针");

        var bodies = ReadSelection(address => mem.ReadU32(address), address => mem.Read(address, 1)[0],
            imageBase + data.Globals.SelectionList.RvaFor(version));
        var applied = 0;
        foreach (var body in bodies)
        {
            if (!IsSelectedBody(address => mem.ReadU32(address), address => mem.Read(address, 1)[0], body)) continue;
            if (ApplyOne(mem, action, body, state)) applied++;
        }
        return applied;
    }

    public static uint[] ReadSelection(Func<nuint, uint> readU32, Func<nuint, byte> readByte,
        nuint global)
    {
        var root = readU32(global);
        if (root < 0x10000) return [];
        var sentinel = (nuint)root + 0x50;
        var count = readU32(root + 0x5Cu);
        if (count == 0) return [];
        if (count > 4096) throw new InvalidOperationException("选中列表计数异常");
        var node = (nuint)readU32(sentinel);
        var visited = new HashSet<nuint>();
        var bodies = new HashSet<uint>();
        for (var i = 0u; i < count; i++)
        {
            if (node == sentinel || node < 0x10000 || !visited.Add(node))
                throw new InvalidOperationException("选中列表链结构异常");
            var drawable = readU32(node + 8);
            if (drawable >= 0x10000 && (readByte(drawable + 0x13Du) & 0x40) != 0)
            {
                var body = readU32(drawable + 0x138u);
                if (body >= 0x10000 && readU32(body + 0xF4u) == drawable)
                    bodies.Add(body);
            }
            node = readU32(node);
        }
        if (node != sentinel || readU32(root + 0x5Cu) != count || readU32(global) != root)
            throw new InvalidOperationException("选中列表已变化，请重新执行");
        return bodies.ToArray();
    }

    public static bool IsSelectedBody(Func<nuint, uint> readU32,
        Func<nuint, byte> readByte, uint body)
    {
        if (body < 0x10000) return false;
        var drawable = readU32(body + 0xF4u);
        return drawable >= 0x10000 && readU32(drawable + 0x138u) == body &&
            (readByte(drawable + 0x13Du) & 0x40) != 0;
    }

    public static uint[] ReadLocomotors(Func<nuint, uint> readU32, uint body, bool allModes)
    {
        var ai = readU32(body + 0x374u);
        if (ai < 0x10000) return [];
        var result = new HashSet<uint>();
        var active = readU32(ai + 0x21Cu);
        if (active >= 0x10000) result.Add(active);
        if (allModes)
        {
            foreach (var setOffset in new uint[] { 0x1FC })
            {
                var begin = readU32(ai + setOffset + 4);
                var end = readU32(ai + setOffset + 8);
                if (begin == end) continue;
                if (begin < 0x10000 || end < begin || end - begin > 4096 || (end - begin) % 4 != 0)
                    throw new InvalidOperationException("移动模式数组异常");
                for (var cursor = begin; cursor < end; cursor += 4)
                {
                    var locomotor = readU32(cursor);
                    if (locomotor >= 0x10000) result.Add(locomotor);
                }
            }
        }
        return result.ToArray();
    }

    public static bool CanGainExperience(Func<nuint, uint> readU32,
        Func<nuint, byte> readByte, uint tracker)
    {
        if (tracker < 0x10000) return false;
        var wrapper = readU32(tracker + 4u);
        if (wrapper < 0x10000) return false;
        var template = readU32(wrapper + 0x14u);
        return template >= 0x10000 && readByte(template + 0x245u) != 0;
    }

    /// <summary>Eligible (body, drawable, tracker) triples for the game-thread rank bridge.
    /// Same validation gates as RankDispatcher so host and consumer agree.</summary>
    public static List<(uint body, uint drawable, uint tracker)> EnumerateRankTargets(
        IInjectionMemory mem, FeaturesData data, string version, nuint imageBase)
    {
        var bodies = ReadSelection(address => mem.ReadU32(address), address => mem.Read(address, 1)[0],
            imageBase + data.Globals.SelectionList.RvaFor(version));
        var targets = new List<(uint, uint, uint)>();
        foreach (var body in bodies)
        {
            if (!IsSelectedBody(address => mem.ReadU32(address), address => mem.Read(address, 1)[0], body)) continue;
            var drawable = mem.ReadU32(body + 0xF4u);
            var tracker = mem.ReadU32(body + 0x3CCu);
            if (drawable < 0x10000 || tracker < 0x10000) continue;
            if (!CanGainExperience(address => mem.ReadU32(address), address => mem.Read(address, 1)[0], tracker)) continue;
            targets.Add((body, drawable, tracker));
        }
        return targets;
    }

    private static uint LocalSide(IInjectionMemory mem, FeaturesData data, string version, nuint imageBase)
    {
        var root = mem.ReadU32(imageBase + data.Globals.PlayerRoot.RvaFor(version));
        return root < 0x10000 ? 0 : mem.ReadU32(root + 0x28u);
    }

    /// <summary>Capturable targets: still selected, cross-linked, and NOT already on the
    /// local side (capture bridge also re-checks in the game thread).</summary>
    public static List<(uint body, uint drawable)> EnumerateCaptureTargets(
        IInjectionMemory mem, FeaturesData data, string version, nuint imageBase)
    {
        var side = LocalSide(mem, data, version, imageBase);
        var bodies = ReadSelection(address => mem.ReadU32(address), address => mem.Read(address, 1)[0],
            imageBase + data.Globals.SelectionList.RvaFor(version));
        var targets = new List<(uint, uint)>();
        if (side == 0) return targets;
        foreach (var body in bodies)
        {
            if (!IsSelectedBody(address => mem.ReadU32(address), address => mem.Read(address, 1)[0], body)) continue;
            if (mem.ReadU32(body + 0x418u) == side) continue;
            var drawable = mem.ReadU32(body + 0xF4u);
            if (drawable < 0x10000) continue;
            targets.Add((body, drawable));
        }
        return targets;
    }

    /// <summary>Destroyable targets: still selected with a live HP component
    /// (kill bridge re-validates cross-links and hp in the game thread).</summary>
    public static List<(uint body, uint drawable, uint hp)> EnumerateKillTargets(
        IInjectionMemory mem, FeaturesData data, string version, nuint imageBase)
    {
        var bodies = ReadSelection(address => mem.ReadU32(address), address => mem.Read(address, 1)[0],
            imageBase + data.Globals.SelectionList.RvaFor(version));
        var targets = new List<(uint, uint, uint)>();
        foreach (var body in bodies)
        {
            if (!IsSelectedBody(address => mem.ReadU32(address), address => mem.Read(address, 1)[0], body)) continue;
            var drawable = mem.ReadU32(body + 0xF4u);
            var hp = mem.ReadU32(body + 0x33Cu);
            if (drawable < 0x10000 || hp < 0x10000) continue;
            targets.Add((body, drawable, hp));
        }
        return targets;
    }

    // Ore node layout verified live (2026-10-11): body+0x398 → state C;
    // [C+4] → container O; [O+8] = amount, [C+0x14] = extracted;
    // remaining = [O+8] - [C+0x14] (matches the FINAL3 ore accessor site).
    private const uint OreStateOff = 0x398;

    /// <summary>Restore every selected ore node to 100000 and reset the extracted
    /// counters of all states pointing at the same container.</summary>
    public static int RestoreOreMines(IInjectionMemory mem, FeaturesData data, string version, nuint imageBase)
    {
        var bodies = ReadSelection(address => mem.ReadU32(address), address => mem.Read(address, 1)[0],
            imageBase + data.Globals.SelectionList.RvaFor(version));
        var restored = 0;
        foreach (var body in bodies)
        {
            var state = mem.ReadU32(body + OreStateOff);
            if (state < 0x10000) continue;
            var container = mem.ReadU32(state + 4u);
            if (container < 0x10000) continue;
            var amount = mem.ReadU32(container + 8u);
            if (amount is 0 or > 5_000_000) continue;
            if (mem.ReadU32(state + 0x14u) > amount) continue;
            // 所有指向同一容器的采集状态一起清零（深度≤2 的指针图遍历，带界）
            var seen = new HashSet<uint> { body };
            var queue = new Queue<uint>();
            queue.Enqueue(body);
            var resets = 0;
            while (queue.Count > 0 && resets < 64)
            {
                var node = queue.Dequeue();
                byte[] block;
                try { block = mem.Read(node, 0x800); }
                catch { continue; }
                if (block.Length < 0x800) continue;
                var cand = BitConverter.ToUInt32(block, (int)OreStateOff);
                if (cand >= 0x10000 && mem.ReadU32(cand + 4u) == container)
                {
                    mem.Write(cand + 0x14u, BitConverter.GetBytes(0u));
                    resets++;
                }
                for (var off = 0; off + 4 <= 0x800; off += 4)
                {
                    var next = BitConverter.ToUInt32(block, off);
                    if (next < 0x1000000 || next > 0x14000000) continue;
                    if (next == container || !seen.Add(next)) continue;
                    if (queue.Count < 64) queue.Enqueue(next);
                }
            }
            mem.Write(container + 8u, BitConverter.GetBytes(100000u));
            restored++;
        }
        return restored;
    }

    private static bool ApplyOne(IInjectionMemory mem, string action, uint body, SelectionActionState? state)
    {
        switch (action)
        {
            case "lv":
            {
                var lv = mem.ReadU32(body + 0x3CC);
                if (!CanGainExperience(address => mem.ReadU32(address), address => mem.Read(address, 1)[0], lv)) return false;
                mem.WriteF32(lv + 0xC, 999999f);
                return true;
            }
            case "speed1":
            case "speed2":
            case "freeze1":
            case "freeze2":
            case "speedrestore":
            {
                var locomotors = ReadLocomotors(address => mem.ReadU32(address), body, action == "speedrestore");
                var speed = action switch
                {
                    "speed2" => 10f,
                    "freeze1" => 0f,
                    _ => 500f,
                };
                var changed = false;
                foreach (var locomotor in locomotors)
                {
                    if (action == "speedrestore")
                        changed |= state?.RestoreSpeed(mem, locomotor) == true;
                    else if (state != null)
                        changed |= state.SetSpeed(mem, locomotor, speed);
                    else
                    {
                        mem.WriteF32(locomotor + 8u, speed);
                        changed = true;
                    }
                    // Keep the game's live speed ceiling and slowdown effects.
                    // Group speed overrides may supersede this base value.
                }
                return changed;
            }
            case "hpmax":
            {
                var hp = mem.ReadU32(body + 0x33C);
                if (hp == 0) return false;
                mem.WriteF32(hp + 4, 999999f);
                mem.WriteF32(hp + 0xC, 999999f);
                return true;
            }
            case "hpmin":
            {
                var hp = mem.ReadU32(body + 0x33C);
                if (hp == 0) return false;
                mem.WriteF32(hp + 4, 1f);
                return true;
            }
            case "hpnormal":
            case "heal":
            {
                var hp = mem.ReadU32(body + 0x33C);
                if (hp < 0x10000) return false;
                var restoreMaximum = action == "hpnormal";
                var maxv = mem.ReadF32(hp + (restoreMaximum ? 0x10u : 0xCu));
                if (!float.IsFinite(maxv) || maxv <= 0f) return false;
                mem.WriteF32(hp + 4, maxv);
                if (restoreMaximum) mem.WriteF32(hp + 0xC, maxv);
                return true;
            }
            case "capture":
            {
                throw new NotSupportedException("归属切换流程尚未验证");
            }
            case "destroy":
            {
                throw new NotSupportedException("摧毁需要游戏线程死亡回调，不能仅覆盖生命值");
            }
            default:
                return false;
        }
    }
}
