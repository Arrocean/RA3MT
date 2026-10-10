using RA3MT.Core.Engine;
using RA3MT.Core.Memory;
using RA3MT.Core.Model;

namespace RA3MT.Core.Features;

/// <summary>One-shot "selected units" actions.
///
/// Chain verified live on the repack builds (2026-10-10 night session):
///   entry+8 → A → A+0x10 → body
///   body+0x33C → HP object (+4 current / +C displayed / +10 max, floats)
///   body+0x418 → owner SIDE object pointer (repack; was an index in EA)
///   [playerEsi+0x1188] → local side object (playerEsi captured by money_h1 stub)
/// Selected entries are enumerated by the zoom stub's capture array.</summary>
public static class SelectionActions
{
    public static int Apply(ProcessMemory mem, FeaturesData data, string version,
        string action, MasterCode mc)
    {
        // 1) 武装捕获，等一帧迭代
        mc.ArmSelectionCapture(true);
        Thread.Sleep(400);
        var entries = mc.ReadCapturedSelection();
        if (entries.Length == 0) return 0;

        // 2) 本地阵营对象（俘虏功能用）
        nuint? localSide = null;
        var diag = mc.ReadDiagnostics();
        if (diag != null && diag.Value.esi > 0x10000)
        {
            var side = mem.ReadU32(diag.Value.esi + MasterCode.SideFieldOff);
            if (side != 0) localSide = side;
        }

        var applied = 0;
        foreach (var e in entries.Distinct())
        {
            if (e < 0x10000) continue;
            try
            {
                var a = mem.ReadU32(e + 8);          // entry+8 → A
                if (a < 0x10000) continue;
                var body = mem.ReadU32(a + 0x10);    // A+0x10 → body
                if (body < 0x10000) continue;
                if (ApplyOne(mem, data, version, action, body, localSide)) applied++;
            }
            catch { /* 单个条目失败不影响其余 */ }
        }
        return applied;
    }

    private static bool ApplyOne(ProcessMemory mem, FeaturesData data,
        string version, string action, uint body, nuint? localSide)
    {
        switch (action)
        {
            case "lv":
            {
                var lv = mem.ReadU32(body + 0x3CC);
                if (lv == 0) return false;
                mem.WriteF32(lv + 0xC, 999999f);
                return true;
            }
            case "speed1":
            {
                var sp = mem.ReadU32(body + 0x374);
                if (sp == 0) return false;
                var node = mem.ReadU32(sp + 0x200);
                if (node == 0) return false;
                var x = mem.ReadU32(node);
                if (x == 0) return false;
                mem.WriteF32(x + 8, 500f);
                return true;
            }
            case "speed2":
            {
                var sp = mem.ReadU32(body + 0x374);
                if (sp == 0) return false;
                var node = mem.ReadU32(sp + 0x200);
                if (node == 0) return false;
                var y = mem.ReadU32(node + 4);
                if (y == 0) return false;
                mem.WriteF32(y + 8, 500f);
                return true;
            }
            case "freeze1":
            {
                var sp = mem.ReadU32(body + 0x374);
                if (sp == 0) return false;
                var node = mem.ReadU32(sp + 0x1FC);
                if (node == 0) return false;
                var x = mem.ReadU32(node);
                if (x == 0) return false;
                mem.WriteF32(x + 8, 0f);
                return true;
            }
            case "freeze2":
            {
                var sp = mem.ReadU32(body + 0x374);
                if (sp == 0) return false;
                var node = mem.ReadU32(sp + 0x1FC);
                if (node == 0) return false;
                var y = mem.ReadU32(node + 4);
                if (y == 0) return false;
                mem.WriteF32(y + 8, 0f);
                return true;
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
            {
                var hp = mem.ReadU32(body + 0x33C);
                if (hp == 0) return false;
                var maxv = mem.ReadF32(hp + 0x10);
                mem.WriteF32(hp + 4, maxv);
                mem.WriteF32(hp + 0xC, maxv);
                return true;
            }
            case "capture":
            {
                if (localSide == null) return false;
                mem.WriteU32(body + 0x418, (uint)localSide.Value);
                return true;
            }
            case "destroy":
            {
                var hp = mem.ReadU32(body + 0x33C);
                if (hp == 0) return false;
                mem.WriteF32(hp + 4, 0f);
                return true;
            }
            default:
                return false;
        }
    }
}
