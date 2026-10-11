# FINAL3 初步解构与移植方向

## 来源与提取

输入：`C:\Users\14560\Downloads\3DMGAME-Com1.12.ken22265.160913\RedAlert3_Trainer_1.12_FINAL3.exe`

- 文件大小：1,422,021 字节。
- SHA256：`5ddd338ec638e01f82454859db6629d57af4123176c88be7cb33adad3b57e7e9`。
- Delphi / Cheat Engine 生成的32位PE，ImageBase `0x400000`，入口RVA `0x75B10`。
- CODE/DATA/BSS 等节，没有UPX标记；native入口已用capstone反汇编，未执行二进制。
- 附加数据从文件偏移 `0x8D000` 开始。表头含33条记录，主记录MustEnableCode。
- 脚本为长度前缀数据：脚本字节与 `(index+1)&0xFF` XOR；地址字符串种子为2。
- 已提取13段ENABLE脚本，其中主脚本偏移 `0x8D05B`，19,604字节、1141行。
- 主脚本自述：游戏 `1.12.3444.25830`，Script Final.3 (3.3)，Ken22265，December 2009，CE5.5。
- 产物：`artifacts/final3/manifest.json` 与各 `.cea`；可重复工具 `tools/analysis/extract_final3.py`。

## 关键差异

### 功能归属明确

FINAL3主脚本明确标注：

- EA RVA `0x128735` 是 Select Unit Ammo，写 Weapon条目+0x1C为 `0x7FFFFFFF`。
- EA RVA `0x438ED0` 是 Danger Level，读取Body+0x1278，写组件+8为50000或0。
- 这直接支持此前静态/活体得出的“原xp999站点实际弹夹，原ammo站点实际威胁等级”结论。
- 弹药记录 Ammo MAX写iEnable+12=0x01，Ammo MAX 2写同地址=0x00；后者实际为关闭，不是第二条弹药链。
- Danger Max/Min/Normal分别写iEnable+13=0x01/0x02/0x00；关闭只停止覆盖，不保存/恢复旧威胁值。

### 游戏线程动作分派

资金结算EA RVA `0x6CFDFE` 重放资金指令后检查 `iEnable+0x20`。
每次资金结算都可能消费尚未执行的动作请求：非零时到MustCode+600，call MustCode+700分派，
执行完清零请求并返回游戏。调用上下文是正常游戏线程，且至少等待资金结算事件触发。
这不是专用update tick，不应声称低延迟/帧级响应；iEnable+20是未原子访问的共享dword。
这是FINAL2a远程createthread动作方案之外的重要新依据。

主分派请求：

| 请求 | 动作 |
|---|---|
| 1 | 超高速移动 |
| 2 | 低速移动 |
| 3 | 冻结 |
| 4 | 恢复速度 |
| 5 | 生命MAX |
| 6 | 生命MIN |
| 7 | 恢复正常生命 |
| 8 | 晋级 |
| 9 | 更改属主ID |
| A | 摧毁 |
| B | 获取基地 |
| C | We Need Back |
| D | 复制单位 |

热键LevelUP记录文件偏移0x92315：地址payload偏移0x92348、长度10、XOR种子2得到`iEnable+20`，请求值字符串`0x08`。
独立遍历所有同key地址payload确认：Level/速度1/速度2/冻结/恢复速度/HP MAX/MIN/NORMAL/ID/摧毁/Base/Copy/WeNeedBack 全写 iEnable+20，分别对应请求码08/01/02/03/04/05/06/07/09/0A/0B/0D/0C；弹药1/2都写 iEnable+12，威胁 Max/Min/Normal写 iEnable+13，OreMine写 iEnable+14。

### 晋级函数的重打包配对结果

FINAL3旧EA调用 `push 0; push 1; push 3` 的真实重打包对应已确认：

| 版本 | 函数VA | RVA | 长度 | 返回 |
|---|---:|---:|---:|---:|
| 1.13 | 0x785600 | 0x385600 | 99 bytes | ret 0xC |
| 1.12 | 0x79A840 | 0x39A840 | 99 bytes | ret 0xC |

两版21字节入口保护和99字节带通配地址的完整AOB各自唯一；非地址指令布局一致。
ECX是ExperienceTracker，参数1是正的晋级增量次数，参数2/3是传给XP award的两个标志。
函数每轮通过阈值查询取得下一等级所需经验，再调用自然XP award；因此请求3表示最多尝试三级，
会在资格、等级上限或经验路径拒绝时提前结束，并不保证一定到三星。

阈值/XP处理器：1.13 `0x5213C0` / `0x76DF90`，1.12 `0x538F90` / `0x781EB0`。
已生成 `artifacts/final3/rank_pair.json`，并运行 `tools/analysis/verify_final3_rank.py`：
两版本结构、相对调用、参数顺序、正/非正次数、四种标志组合和提前停止共160个Unicorn模拟用例通过。
模拟替换了两个游戏helper，仅证明调用约定和控制流，不证明游戏资格或画面效果。

尚未接入RA3MT：需要把请求放进已证明的游戏线程分派桥，并为1.13/1.12制作请求状态的原子/生命周期处理。
直接从WPF线程调用0x785600或0x705F60仍不安全。
工程新增 `RankApiResolver`：只读验证版本入口、完整99字节特征、上下文全局和两个相对helper目标，
`SelfCheck ranktest` 对1.12/1.13真实镜像通过，并拒绝每版4种篡改（指令、全局、两个helper位移）。
这保证将来动作桥拿到的目标仍是配对函数，但不执行该函数。

### 晋级请求桥离线验证

新增 `RankDispatcher.Emit`，对应未来游戏线程CALL目标；邮箱要求state=1时原子领取为2，
验证Body/Drawable/Tracker/选中位/属主/经验资格链，调用配对rank API（ECX tracker，push0/1/3），
记录rank前后并将状态置3成功或4拒绝。FXSAVE/FXRSTOR保护x87/MXCSR/XMM，保存全部GPR/EFLAGS/ESP。
未解决的游戏对象销毁竞态仍需在游戏线程语义下处理；非空旧堆地址不是安全证明。
`test_rank_dispatcher.py`现有218个Unicorn用例通过，覆盖16栈对齐、4种rank结果、标志、递归state2、
所有关系/资格/低地址门禁、不可写payload和浮点/寄存器恢复。仅离线验证，未接入money_h2，未向游戏注入。

- FINAL3把加速/低速/冻结前的速度保存在Locomotor+0x40，再恢复到+8。
- 操作+0x200数组第一项，并根据第二项+0x18检查进行处理；仍存在空指针和模式假设，不能直接复制。
- 慢速脚本中`mov ebx,[ebx+138]`后却测试/解引用EAX，属于待复核的明显可疑寄存器使用。
- 恢复NormalHP读取健康组件+0x10，然后写+4和+0xC。
  这定义为恢复基准最大生命并治疗，不同于RA3MT后来实现的仅按有效上限治疗。
  界面应该区分“恢复正常生命上限”和“治疗至当前上限”，不能把原版语义误判为字段错误。

### 俘虏仍不可直接照搬

FINAL3 ChangeID在排除几个模板ID后仍直接写Body+0x418，不调用完整归属transition。
因此新版本也不能作为直接字段覆盖安全性的证明。
此前定位的完整transition与真实capture调用链仍有价值。

### 新功能与标志

可见记录包括 Enemy Can't Build、Player God Mode、Player One Kill Mode、Free Build、Get Me Base、Copy For Me、We Need Back。
主脚本新增ID捕获EA RVA0xFF95B，读取[EAX+28]与其+20记录阵营/索引。
资金改为请求一次加100000并清标志，而非无限每次增加；协议点数写15，而非99。
Map桩先原始写入再写100000，单位动作在游戏线程内执行。

## 游戏线程动作桥进展（未接入生产钩子）

已新增 `RankRequestMailbox` 与 `SelfCheck rankmailboxtest`，邮箱位于未来MasterCode块+0x1800：
state +0x00、Body +0x04、Drawable +0x08、Tracker +0x0C、rankBefore/+After +0x10/+0x14。
提交只允许state 0/3/4，先写20字节目标快照，最后写state=1；state1/2拒绝覆盖；
非法指针和写入失败不发布请求。12个离线生命周期/发布顺序用例通过。
真正的 x86 游戏线程消费桩尚在实现/审查中，不能把邮箱测试当成游戏效果验证。

以FINAL3作为主要参考；当前生产版本没有执行FINAL3二进制，也没有向游戏写入。
此前v13保留作历史实验版；新的生产改动须通过双版本静态配对、离线执行测试和受控实机测试。

下一步以FINAL3作为主要参考：

1. 定位晋级EA+35C200、摧毁EA+39EA50在重打包1.12/1.13的真实函数，核实参数和资格过滤。
2. 采用有边界/状态协议的游戏线程动作请求，避免旧脚本无锁覆盖、无限链循环和寄存器破坏。
3. 重新定义速度恢复、正常生命恢复、威胁等级及矿脉动作，保留已经有独立证据的字段定位。
4. 继续使用完整归属切换路径，而非FINAL3的直接属主写入。
5. 执行单机受控复测再声称功能生效；现有离线用例只能证明代码合成输入契约。
