using RA3MT.Core.Features.Abstractions;
using RA3MT.Core.Model;

namespace RA3MT.Core.Features.Patches;

/// <summary>"Build anywhere": a two-byte branch patch at the placement gate.
///
/// FINAL3 flipped the branch at the tail of the placement validator — the
/// "every candidate failed → return failure code 2 (out of buildable range)" path —
/// from <c>75 0C</c> (jne) to <c>EB 0C</c> (jmp). With the jump, code 2 is never
/// returned, so cells outside the buildable area pass. Verified live on
/// 2026-10-12: the ghost still renders grey but the click places the structure.
///
/// The patch is a pure code-byte switch: it survives a match restart and is
/// restored on detach. It is versioned through the feature's own private offset
/// (features.json <c>globals.buildAnywherePatch</c>), not a shared game global.
/// </summary>
public sealed class BuildAnywhereFeature : IFeature
{
    public const string FeatureId = "build_anywhere";

    private static readonly byte[] BranchTaken = { 0xEB, 0x0C };   // jmp +0x0C
    private static readonly byte[] BranchNotTaken = { 0x75, 0x0C }; // jne +0x0C

    public string Id => FeatureId;
    public FeatureKind Kind => FeatureKind.Toggle;
    public FeatureAvailability Availability => FeatureAvailability.Ready;
    public bool IsMigrated => true;

    public IFeatureState CreateState(FeatureContext context) => new State(context);

    private sealed class State(FeatureContext context) : IFeatureState
    {
        private bool _on;

        public bool IsOn => _on;

        public FeatureResult SetOn(bool on)
        {
            // Fail closed: with no attached session there is no memory service and
            // the site cannot be validated.
            var memory = context.Host.Services.Get<Host.IGameMemory>();
            if (memory is null) return FeatureResult.Failure("未附加或未安装");

            var site = ResolveSite(memory, out var reason);
            if (site == 0) return FeatureResult.Failure(reason);

            var current = memory.ReadBytes(site, 2);
            var desired = on ? BranchTaken : BranchNotTaken;

            if (current.SequenceEqual(desired))
            {
                _on = on;
                return FeatureResult.Succeeded(on ? "已在开启状态" : "已在关闭状态");
            }

            if (!current.SequenceEqual(BranchNotTaken) && !current.SequenceEqual(BranchTaken))
                return FeatureResult.Failure($"补丁点字节异常（{Convert.ToHexString(current)}），拒绝改写");

            memory.WriteBytes(site, desired);
            if (!memory.ReadBytes(site, 2).SequenceEqual(desired))
                return FeatureResult.Failure("写入校验失败");

            _on = on;
            context.Host.NotifyStateChanged();
            return FeatureResult.Succeeded(on ? "放置范围限制已解除" : "放置范围限制已恢复");
        }

        public FeatureResult Execute(string? arg) => FeatureResult.Failure("非动作型功能");

        /// <summary>The feature's own patch offset, taken from the model's
        /// feature-private section rather than a shared game global.</summary>
        private nuint ResolveSite(Host.IGameMemory memory, out string reason)
        {
            reason = "";
            var rva = PrivateOffsets.RvaFor(context.Data, context.Version, FeatureId, "site");
            if (rva == 0)
            {
                reason = "本版本暂不支持（补丁点未注册）";
                return 0;
            }
            return context.ImageBase + rva;
        }
    }
}
