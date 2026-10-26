using RA3MT.Core.Features;
using RA3MT.Core.Features.Abstractions;
using RA3MT.Core.Features.Actions;
using RA3MT.Core.Features.EngineAdapters;
using RA3MT.Core.Features.Host;
using RA3MT.Core.Memory;
using RA3MT.Core.Model;

namespace RA3MT.SelfCheck;

public static class ActionChecks
{
    private sealed class Memory : IInjectionMemory
    {
        public readonly Dictionary<nuint, byte> Bytes = new();
        public readonly List<nuint> Writes = new();
        public byte[] Read(nuint address, int size) => Enumerable.Range(0, size)
            .Select(i => Bytes.GetValueOrDefault(address + (nuint)i)).ToArray();
        public void Write(nuint address, ReadOnlySpan<byte> data)
        {
            Writes.Add(address);
            for (var i = 0; i < data.Length; i++) Bytes[address + (nuint)i] = data[i];
        }
        public nuint Alloc(nuint size, uint protect = 0x40) => throw new NotSupportedException();
        public void U32(nuint address, uint value) => Write(address, BitConverter.GetBytes(value));
    }

    public static void Run()
    {
        var data = FeaturesData.LoadEmbedded();
        var global = (nuint)(0x400000 + data.Globals.SelectionList.RvaFor("1.13"));
        Memory Fixture(float maximum)
        {
            var memory = new Memory();
            memory.U32(global, 0x20000);
            memory.U32(0x20050, 0x30000);
            memory.U32(0x2005C, 1);
            memory.U32(0x30000, 0x20050);
            memory.U32(0x30008, 0x40000);
            memory.U32(0x40138, 0x50000);
            memory.U32(0x500F4, 0x40000);
            memory.Write(0x4013D, new byte[] { 0x40 });
            memory.U32(0x5033C, 0x60000);
            memory.WriteF32(0x60004, 50);
            memory.WriteF32(0x6000C, maximum);
            memory.WriteF32(0x60010, 100);
            memory.Writes.Clear();
            return memory;
        }
        var count = 0;
        foreach (var maximum in new[] { 200f, 0f, -1f, float.NaN, float.PositiveInfinity })
        {
            var memory = Fixture(maximum);
            var applied = SelectionActions.Apply(memory, data, "1.13", "heal", 0x400000);
            var valid = float.IsFinite(maximum) && maximum > 0;
            if (applied != (valid ? 1 : 0)) throw new Exception("Invalid full-heal outcome");
            if (valid)
            {
                if (memory.ReadF32(0x60004) != maximum || !memory.Writes.SequenceEqual(new nuint[] { 0x60004 }))
                    throw new Exception("Full heal must change only current HP");
            }
            else if (memory.Writes.Count != 0) throw new Exception("Invalid maximum caused write");
            if (memory.ReadF32(0x60010) != 100) throw new Exception("Base maximum changed");
            count++;
        }
        foreach (var baseMaximum in new[] { 100f, 0f, -1f, float.NaN, float.PositiveInfinity })
        {
            var memory = Fixture(999999);
            memory.WriteF32(0x60010, baseMaximum);
            memory.Writes.Clear();
            var applied = SelectionActions.Apply(memory, data, "1.13", "hpnormal", 0x400000);
            var valid = float.IsFinite(baseMaximum) && baseMaximum > 0;
            if (applied != (valid ? 1 : 0)) throw new Exception("Invalid normal-restore outcome");
            if (valid)
            {
                if (memory.ReadF32(0x60004) != baseMaximum || memory.ReadF32(0x6000C) != baseMaximum ||
                    !memory.Writes.SequenceEqual(new nuint[] { 0x60004, 0x6000C }))
                    throw new Exception("Normal restore must reset effective max and current HP");
            }
            else if (memory.Writes.Count != 0) throw new Exception("Invalid base maximum caused write");
            count++;
        }
        foreach (var action in new[] { "capture", "destroy" })
        {
            var memory = Fixture(200);
            var refused = false;
            try { SelectionActions.Apply(memory, data, "1.13", action, 0x400000); }
            catch (NotSupportedException) { refused = true; }
            if (!refused || memory.Writes.Count != 0) throw new Exception("Unsafe action was not refused");
            count++;
        }
        var movement = Fixture(200);
        movement.U32(0x50374, 0x70000);
        movement.U32(0x7021C, 0x80000);
        movement.U32(0x80004, 0x90000);
        movement.WriteF32(0x80008, 35);
        movement.WriteF32(0x80020, 20);
        var movementState = new SelectionActionState();
        foreach (var (action, expected) in new[] { ("speed1", 500f), ("speed2", 10f), ("freeze1", 0f), ("speedrestore", 35f) })
        {
            movement.Writes.Clear();
            if (SelectionActions.Apply(movement, data, "1.13", action, 0x400000, movementState) != 1 ||
                movement.ReadF32(0x80008) != expected || movement.ReadF32(0x80020) != 20)
                throw new Exception("Incorrect FINAL3 speed or restore outcome");
            count++;
        }
        movementState.SetSpeed(movement, 0x80000, 500);
        movement.U32(0x80004, 0xA0000);
        movement.Writes.Clear();
        if (movementState.RestoreSpeed(movement, 0x80000) || movement.Writes.Count != 0)
            throw new Exception("Stale locomotor restored");
        count++;
        movementState.SetSpeed(movement, 0x80000, 10);
        movementState.Clear();
        movement.Writes.Clear();
        if (movementState.RestoreSpeed(movement, 0x80000) || movement.Writes.Count != 0)
            throw new Exception("Previous session speed restored");
        count++;
        movementState.SetSpeed(movement, 0x80000, 500);
        movement.WriteF32(0x80008, 45);
        movement.Writes.Clear();
        if (movementState.RestoreSpeed(movement, 0x80000) || movement.Writes.Count != 0)
            throw new Exception("Changed same-template instance restored");
        count++;
        movementState.SetSpeed(movement, 0x80000, 10);
        movement.Writes.Clear();
        if (!movementState.RestoreSpeed(movement, 0x80000) || movement.ReadF32(0x80008) != 45)
            throw new Exception("Fresh backup did not retain changed original");
        count++;
        foreach (var invalid in new[] { float.NaN, float.PositiveInfinity, -1f })
        {
            movement.Writes.Clear();
            if (movementState.SetSpeed(movement, 0x80000, invalid) || movement.Writes.Count != 0)
                throw new Exception("Invalid speed written");
            count++;
        }
        var deselected = Fixture(200);
        deselected.Write(0x4013D, new byte[] { 0 });
        deselected.Writes.Clear();
        if (SelectionActions.Apply(deselected, data, "1.13", "hpnormal", 0x400000) != 0 || deselected.Writes.Count != 0)
            throw new Exception("Deselected target changed");

        // Spawn anchor gate: the trainer-side anchor (mouse-ground copy, else the
        // selection) is only the fallback for when the game-thread transform
        // fails. Versions with no mouseGround offset (1.12 / 1.12ea) and nothing
        // selected — hovering over empty ground — must still submit in mouse
        // mode; the stub resolves the live mouse itself.
        var spawnCases = RunSpawnGateCases(data);
        var speedCases = RunSpeedFeatureCases();
        Console.WriteLine($"PASS {count + 1} action-write cases: FINAL3 normal restore, effective-max heal, invalid floats and unsafe action refusal");
        Console.WriteLine($"PASS {spawnCases} spawn anchor-gate cases: MCV/reinforcement submit in mouse mode without any trainer-side anchor");
        Console.WriteLine($"PASS {speedCases} speed feature cases across six builds: shared restore, repeated writes, selection/mode changes and session isolation");
    }

    // Exercise distinct catalog features, as the UI does. Passing one state
    // directly to SelectionActions for every action misses per-feature backups.
    private static int RunSpeedFeatureCases()
    {
        var cases = 0;
        foreach (var version in new[] { "1.12", "1.13", "1.12ea", "uprising-1.0ea", "uprising-1.0", "uprising-1.01" })
        {
            var data = FeaturesData.LoadEmbedded(GameLayout.IsUprising(version) ? GameId.Uprising : GameId.RedAlert3);
            var layout = GameLayout.For(version);
            var catalog = FeatureCatalog.Build(data);
            var ids = new[] { "sel_speed", "sel_speed2", "sel_freeze", "sel_freeze2" };
            void Check(bool ok, string reason)
            {
                if (!ok) throw new Exception($"{version} speed feature regression: {reason}");
                cases++;
            }
            Memory Fixture(int selected = 1)
            {
                var m = new Memory();
                var sentinel = 0x20000u + layout.SelectionHead;
                m.U32(0x400000 + data.Globals.SelectionList.RvaFor(version), 0x20000);
                m.U32(sentinel, 0x30000); m.U32(0x20000 + layout.SelectionCount, (uint)selected);
                for (var i = 0u; i < 2; i++)
                {
                    var node = 0x30000u + i * 0x40;
                    var draw = 0x40000u + i * 0x1000;
                    var body = 0x50000u + i * 0x1000;
                    var ai = 0x70000u + i * 0x1000;
                    var loc = 0x80000u + i * 0x1000;
                    var array = 0xA0000u + i * 0x1000;
                    m.U32(node, i + 1 < selected ? node + 0x40 : sentinel);
                    m.U32(node + 8, draw); m.U32(draw + 0x138, body);
                    m.Write(draw + 0x13D, new byte[] { 0x40 }); m.U32(body + layout.BodyDrawable, draw);
                    m.U32(body + layout.Ai, ai); m.U32(ai + layout.LocomotorActive, loc);
                    m.U32(ai + layout.LocomotorSet + 4, array); m.U32(ai + layout.LocomotorSet + 8, array + 4);
                    m.U32(array, loc); m.U32(loc + 4, 0x90000u + i * 0x1000);
                    m.WriteF32(loc + 8, i == 0 ? 35 : 70);
                }
                m.Writes.Clear();
                return m;
            }
            Dictionary<string, IFeatureState> States(Memory m, SelectionActionState? speeds)
            {
                var services = new FeatureServiceRegistry();
                if (speeds is not null) services.Register(speeds);
                var context = new FeatureContext
                {
                    Session = new SessionSnapshot
                    {
                        Memory = m, Version = version, ImageBase = 0x400000, Pid = 0,
                        ProcessPath = "", ResolvedSites = 0, TotalSites = 0,
                    },
                    Data = data, Symbols = null!,
                    Host = new FeatureHost
                    {
                        Memory = m, Services = services, Symbols = null!,
                        Log = _ => { }, NotifyStateChanged = () => { },
                    },
                };
                return ids.ToDictionary(id => id, id =>
                {
                    if (!catalog.TryGet(id, out var feature)) throw new Exception("Missing speed feature: " + id);
                    return feature.CreateState(context);
                });
            }
            foreach (var sequence in new[]
            {
                new[] { ("sel_speed", 500f), ("sel_freeze2", 35f) },
                new[] { ("sel_speed2", 10f), ("sel_freeze2", 35f) },
                new[] { ("sel_freeze", 0f), ("sel_freeze2", 35f) },
                new[] { ("sel_speed", 500f), ("sel_speed2", 10f), ("sel_freeze", 0f), ("sel_freeze2", 35f) },
                new[] { ("sel_speed", 500f), ("sel_speed", 500f), ("sel_freeze2", 35f) },
            })
            {
                var m = Fixture(); var states = States(m, new SelectionActionState());
                foreach (var (id, expected) in sequence)
                    Check(states[id].Execute(null).Ok && m.ReadF32(0x80008) == expected, id + " must preserve the original speed across features");
            }
            var memory = Fixture(); var shared = new SelectionActionState(); var current = States(memory, shared);
            Check(current["sel_speed"].Execute(null).Ok, "speed before feature recreation");
            current = States(memory, shared);
            Check(current["sel_freeze2"].Execute(null).Ok && memory.ReadF32(0x80008) == 35, "recreated features use session backup");

            memory = Fixture(); current = States(memory, new SelectionActionState());
            Check(current["sel_speed"].Execute(null).Ok, "speed before locomotor switch");
            memory.U32(0x70000 + layout.LocomotorActive, 0x81000);
            Check(current["sel_freeze2"].Execute(null).Ok && memory.ReadF32(0x80008) == 35 && memory.ReadF32(0x81008) == 70,
                "restore saved inactive mode without changing unmodified active mode");

            memory = Fixture(2); current = States(memory, new SelectionActionState());
            Check(current["sel_speed"].Execute(null).Ok && memory.ReadF32(0x80008) == 500 && memory.ReadF32(0x81008) == 500, "box selection speed");
            Check(current["sel_freeze2"].Execute(null).Ok && memory.ReadF32(0x80008) == 35 && memory.ReadF32(0x81008) == 70, "each selected unit has its own original speed");

            memory = Fixture(); shared = new SelectionActionState(); current = States(memory, shared);
            Check(current["sel_speed"].Execute(null).Ok, "speed before session end");
            var next = States(memory, new SelectionActionState()); memory.Writes.Clear();
            Check(!next["sel_freeze2"].Execute(null).Ok && memory.Writes.Count == 0, "another session cannot consume old backup");
            shared.Clear();
            Check(!current["sel_freeze2"].Execute(null).Ok && memory.Writes.Count == 0, "session cleanup clears all speed feature backups");

            memory = Fixture(); current = States(memory, null);
            Check(!current["sel_speed"].Execute(null).Ok && memory.Writes.Count == 0, "missing shared speed service refuses untracked writes");
        }
        return cases;
    }

    /// <summary>Exercises SpawnActionFeature against a stub gateway: every
    /// anchor combination must submit (mouse mode), with the anchor staged as
    /// the transform-failure fallback; an inactive bridge still fails closed.</summary>
    private static int RunSpawnGateCases(FeaturesData data)
    {
        var count = 0;
        (FeatureResult result, List<(uint, uint, float, float, float)> submitted, List<string> logs) Run(
            SpawnActionKind kind, string? arg,
            (float x, float y, float z)? mouseGround, (float x, float y, float z)? selectionAnchor, bool active = true)
        {
            var submitted = new List<(uint, uint, float, float, float)>();
            var logs = new List<string>();
            var gateway = new SpawnGateway(active, () => Array.Empty<uint>(),
                () => mouseGround, () => selectionAnchor,
                (_, requests) => (true, ""),
                (_, _, x, y, z, _) => { submitted.Add((0, 0, x, y, z)); return (true, ""); },
                (_, requests) => { submitted.AddRange(requests); return (true, ""); });
            var host = new FeatureHost
            {
                Log = logs.Add,
                NotifyStateChanged = () => { },
                Memory = null!,
                Services = new FeatureServiceRegistry().Register<ISpawnGateway>(gateway),
                Symbols = null!,
            };
            var state = new SpawnActionFeature(kind switch
            {
                SpawnActionKind.Mcv => "mcv_allied",
                _ => "reinforce_code",
            }, kind).CreateState(new FeatureContext
            {
                Session = new SessionSnapshot
                {
                    Memory = null!, Version = "1.12", ImageBase = 0x400000, Pid = 0,
                    ProcessPath = "", ResolvedSites = 0, TotalSites = 0,
                },
                Symbols = null!,
                Data = data,
                Host = host,
            });
            return (state.Execute(arg), submitted, logs);
        }

        // no mouse-ground copy (1.12 / 1.12ea), nothing selected: the live report
        var (result, submitted, logs) = Run(SpawnActionKind.Mcv, "allied", null, null);
        if (!result.Ok || submitted.Count != 1 || submitted[0] != (0x28DA574Eu, 0u, 0f, 0f, 0f))
            throw new Exception("MCV must submit in mouse mode with no anchor at all");
        if (!logs.Any(l => l.Contains("无回退锚点")))
            throw new Exception("MCV no-anchor submission must explain itself in the log");
        count++;

        // no mouse-ground copy but a selected unit: the unit is the fallback
        (_, submitted, _) = Run(SpawnActionKind.Mcv, "soviet", null, (10f, 20f, 30f));
        if (submitted.Count != 1 || submitted[0] != (0xAF4C0DA5u, 0u, 10f, 20f, 30f))
            throw new Exception("MCV fallback must be the selection anchor");
        count++;

        // mouse-ground copy present (1.13): staged as the fallback
        (_, submitted, logs) = Run(SpawnActionKind.Mcv, "japan", (100f, 5f, 200f), null);
        if (submitted.Count != 1 || submitted[0] != (0x1C2EF767u, 0u, 100f, 5f, 200f))
            throw new Exception("MCV fallback must be the mouse ground when available");
        if (!logs.Any(l => l.Contains("鼠标地面")))
            throw new Exception("MCV mouse-ground submission must log the position");
        count++;

        // reinforcement code: same relaxation on the squad path
        (result, submitted, logs) = Run(SpawnActionKind.HashCode, "6586A5A0", null, null);
        if (!result.Ok || submitted.Count != 1 || submitted[0].Item3 != 0f || submitted[0].Item5 != 0f)
            throw new Exception("Reinforcement must submit in mouse mode with no anchor");
        if (!logs.Any(l => l.Contains("无回退锚点")))
            throw new Exception("Reinforcement no-anchor submission must explain itself in the log");
        count++;

        // inactive bridge still fails closed
        (result, submitted, _) = Run(SpawnActionKind.Mcv, "allied", (100f, 5f, 200f), null, active: false);
        if (result.Ok || submitted.Count != 0)
            throw new Exception("Inactive spawn bridge must not submit");
        count++;
        return count;
    }
}
