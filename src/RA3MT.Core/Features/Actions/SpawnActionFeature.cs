using RA3MT.Core.Features.Abstractions;
using RA3MT.Core.Features.Host;
using RA3MT.Core.Model;

namespace RA3MT.Core.Features.Actions;

/// <summary>Spawn-bridge actions: copy the selected unit, place one of the three
/// MCVs, or spawn from a reinforcement hash code.
///
/// All three go through <see cref="ISpawnGateway"/>: the unit/template-chain
/// walking and the mouse-ground lookup belong to the game model, not to the
/// feature, so the feature only decides *which* request to build.</summary>
public sealed class SpawnActionFeature(string id, SpawnActionKind kind) : IFeature
{
    public const string McvAllied = "allied";
    public const string McvSoviet = "soviet";
    public const string McvJapan = "japan";

    public string Id { get; } = id;
    public SpawnActionKind ActionKind { get; } = kind;

    public FeatureKind Kind => FeatureKind.Action;
    public FeatureAvailability Availability => FeatureAvailability.NeedsBridge;
    public bool IsMigrated => true;

    public IFeatureState CreateState(FeatureContext context) => new State(context, this);

    private sealed class State(FeatureContext context, SpawnActionFeature feature) : IFeatureState
    {
        public bool IsOn => false;

        public FeatureResult SetOn(bool on) => FeatureResult.Failure("非开关型功能");

        public FeatureResult Execute(string? arg)
        {
            var gateway = context.Host.Services.Get<ISpawnGateway>();
            if (gateway is null || !gateway.IsActive)
                return FeatureResult.Failure("生成桥未启用（校验未通过，或被环境变量 RA3MT_SPAWN=0 关闭）");

            return feature.ActionKind switch
            {
                SpawnActionKind.CopySelection => CopySelection(gateway),
                SpawnActionKind.Mcv => SpawnMcv(gateway, arg),
                SpawnActionKind.HashCode => SpawnHash(gateway, arg),
                _ => FeatureResult.Failure("未知的生成动作"),
            };
        }

        /// <summary>Copy selected: spawn the same template at the mouse point, or at
        /// the unit's own position when the cursor is not over the map.</summary>
        private FeatureResult CopySelection(ISpawnGateway gateway)
        {
            var holders = gateway.CopyHolders;
            if (holders.Count == 0)
                return FeatureResult.Failure("没有可复制的选中目标（未选中或目标缺少模板链）");

            var mouse = gateway.MouseGround;
            var requests = new List<(uint hash, uint holder, float x, float y, float z)>();
            if (mouse is { } m)
            {
                requests.AddRange(holders.Select(holder => (0u, holder, m.x, m.y, m.z)));
            }
            else
            {
                var a = gateway.SelectionAnchor ?? (0f, 0f, 0f);
                requests.AddRange(holders.Select(holder => (0u, holder, a.x, a.y, a.z)));
            }

            return gateway.SubmitAtMouse(feature.Id, requests);
        }

        private FeatureResult SpawnMcv(ISpawnGateway gateway, string? arg)
        {
            if (!SpawnActions.McvHashes.TryGetValue(arg ?? "", out var hash))
                return FeatureResult.Failure("未知阵营");
            return SpawnAtAnchor(gateway, hash, describe: $"基地车（{arg}）");
        }

        private FeatureResult SpawnHash(ISpawnGateway gateway, string? arg)
        {
            // The embedded table resolves unit names (and localized names);
            // raw community-guide codes still go through the hash parser.
            if (!ReinforcementCatalog.ForVersion(context.Session.Version).TryResolve(arg, out var hash, out var entry) || hash == 0)
                return FeatureResult.Failure("无效的增援代码（8 位十六进制，或用输入框旁的 📋 从单位表选择；也可直接输入单位名）");
            var label = entry is { } e ? $"增援 {e.Zh}（{e.Name}）0x{hash:X8}" : $"增援代码 0x{hash:X8}";
            var mouse = gateway.MouseGround;
            var anchor = mouse ?? gateway.SelectionAnchor;
            if (mouse is { } m)
                context.Host.Log($"{label}：围绕鼠标地面 0x({m.x:F0}, {m.z:F0}) 生成 8 个并升星");
            else if (anchor is null)
                context.Host.Log($"{label}：以实时鼠标位置生成（本版本无鼠标地面缓存且未选中单位，无回退锚点）");
            var (x, y, z) = anchor ?? (0f, 0f, 0f);
            return gateway.SubmitReinforcement(feature.Id, hash, x, y, z);
        }

        /// <summary>Spawn one hash at the live mouse point. The trainer-side
        /// anchor (mouse-ground copy, else the selected unit's position) is only
        /// the fallback for when the game-thread transform fails — versions with
        /// no mouseGround offset (1.12 / 1.12ea) must not be locked out of the
        /// feature, so with no anchor at all the request still submits and the
        /// stub resolves the live mouse itself.</summary>
        private FeatureResult SpawnAtAnchor(ISpawnGateway gateway, uint hash, string describe)
        {
            var mouse = gateway.MouseGround;
            var anchor = mouse ?? gateway.SelectionAnchor;
            if (mouse is { } m)
                context.Host.Log($"{describe} 生成位置=鼠标地面 0x({m.x:F0}, {m.z:F0})");
            else if (anchor is null)
                context.Host.Log($"{describe}：以实时鼠标位置生成（本版本无鼠标地面缓存且未选中单位，无回退锚点）");
            var (x, y, z) = anchor ?? (0f, 0f, 0f);
            return gateway.SubmitAtMouse(feature.Id, [(hash, 0u, x, y, z)]);
        }
    }
}

public enum SpawnActionKind
{
    /// <summary>Copy the selected unit's template.</summary>
    CopySelection,

    /// <summary>Spawn one of the three MCVs (arg = allied/soviet/japan).</summary>
    Mcv,

    /// <summary>Spawn from an 8-hex-digit WB string hash (arg = the code).</summary>
    HashCode,
}
