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

### 真正晋级与摧毁调用

晋级桩：

```asm
mov ecx,eax  ; ExperienceTracker
push 0
push 1
push 3
call ra3_1.12.game+35C200
ret
```

摧毁桩：

```asm
mov ecx,eax  ; Body
push 0
push 19
push 6
call ra3_1.12.game+39EA50
ret
```

这给出了此前缺失的游戏调用与线程分派组合。EA旧RVA不等于本机重打包1.12/1.13的RVA，必须先定位函数并验证参数语义、完整调用约定及浮点/SIMD保存，再移植。

### 速度与正常生命

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

## 当前项目处理原则

本轮用户要求先停下，旧持久修复目标已暂停；未启用新的自动继续目标。
未改RA3MT生产代码、未执行原FINAL3修改器、未向游戏写入。
此前v12保留作历史实验版，不应被当作按FINAL3完整移植的结果。

下一步以FINAL3作为主要参考：

1. 定位晋级EA+35C200、摧毁EA+39EA50在重打包1.12/1.13的真实函数，核实参数和资格过滤。
2. 采用有边界/状态协议的游戏线程动作请求，避免旧脚本无锁覆盖、无限链循环和寄存器破坏。
3. 重新定义速度恢复、正常生命恢复、威胁等级及矿脉动作，保留已经有独立证据的字段定位。
4. 继续使用完整归属切换路径，而非FINAL3的直接属主写入。
5. 执行单机受控复测再声称功能生效；现有离线用例只能证明代码合成输入契约。
