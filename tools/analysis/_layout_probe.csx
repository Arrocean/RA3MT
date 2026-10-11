using RA3MT.Core.Engine;

var layout = BlockLayoutCatalog.Create();
var dispatcherIds = new (string name, int length)[]
{
    ("RankDispatcherCode", 0x3C),
    ("CaptureDispatcherCode", 0x3C),
    ("KillDispatcherCode", 0x3C),
    ("SpawnDispatcherCode", 0x3C),
};
foreach (var (name, len) in dispatcherIds)
{
    var at = layout.OffsetOf(name.Replace("Code", ""));
    layout.DeclareMeasured(name, at, len, name);
}
layout.Declare("StubArena", BlockLayoutCatalog.StubAreaStart, 0x4F0, "probe");
foreach (var r in layout.Regions.OrderBy(r => r.Offset))
    Console.WriteLine($"  0x{r.Offset:X4}-0x{r.End:X4}  {r.Name,-26} {r.Owner}");
Console.WriteLine("errors: " + string.Join(" | ", layout.Errors()));
