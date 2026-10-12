# FINAL3 ↔ Final2a ↔ RA3MT 完整对照审计

> **时效性说明**：本文档为历史交付物，写作于 2026-10-11（v16 时期）。
> 此后的结论演进以 `docs/NOTES.md`（v17 起）为准——特别是 FINAL3 脚本语义（v19b 行为级审计）、
> 随地建造定案（v19）、摧毁完整伤害入口（v19c/v20）已更新本文档中的相应推测。

日期：2026-10-11。本文档是 `/goal` 的交付物：以 FINAL3（RedAlert3_Trainer_1.12_FINAL3.exe，
SHA256 `5ddd338e…7e9`，提取自 artifacts/final3/）为主参考，对照 Final2a 转储
（D:\RA3TrainerWork\scripts_dump.txt）与 RA3MT 当前实现（v16），给出每个脚本/功能/调用路径的
移植状态、验证等级与明确结论。

验证等级图例：
- **L1 活体**：真实游戏进程内验证过效果或字节
- **L2 静态+执行**：双版本二进制字节校验 + Unicorn 模拟执行用例（无游戏进程）
- **L3 静态**：仅文件字节/反汇编定位，未执行
- **L4 推测**：区域插值/单一模式命中，未经交叉确认

## 1. FINAL3 全部 22 个代码站点对照表

| # | FINAL3 功能 | EA RVA | 位移字节 | 重打包 1.12 | 重打包 1.13 | RA3MT 挂钩 | 状态 |
|---|---|---|---|---|---|---|---|
| 1 | PlayerID 捕获 | 0xFF95B | 8B50288B4220 | — | — | 无需挂钩 | 已被 playerRoot 全局+0x28 取代（1.13 活体属主匹配，L1） |
| 2 | 资金+分派 | 0x6CFDFE | 0378048B11 | 0x664E9E | 0x6699CE | money_h2 | L1（资金封顶实测）+晋级桥宿主 |
| 3 | 电力 | 0x6CFD0D | 8B40048B8EB0030000 | 0x664DAD | 0x6698DD | money_h1 | L1（电力满格实测） |
| 4 | 协议点数(=15) | 0x6CFE6C | 8B78348B4E3C | 0x664F0C | 0x669A3C | money_h3 | L2（v15 对齐 15）未实测 |
| 5 | 解锁全协议 | 0x6CFEB5 | F30F10472C | 0x664F55 | 0x669A85 | money_h4 | L2 未实测 |
| 6 | 快建1 | 0x30F42E | F30F2C461C | 0x34D81E | 0x3386CE | proto_cool_b | L1（快速建造实测） |
| 7 | 快建2 | 0x30F38C | D9461C89465C | 0x34D77C | 0x33862C | proto_cool_a | L1 同上 |
| 8 | 快建3 | 0x2F6CFF | D986BC010000 | 0x33511F | 0x31FEDF | power | L1 同上 |
| 9 | 立即就绪 | 0x2EBB69 | 8B9818040000 | 0x329F19 | 0x314D19 | build_power | L2（重写敌我判定+EDI 重载）未实测 |
| 10 | 立即就绪2 | 0x43EC19 | 8B70508B01 | 0x47CB89 | 0x467FC9 | build_hp_a | L2（桩内限界链表搜索）未实测 |
| 11 | 冻结敌方 | 0x43ECA6 | 8B51503B500C | 0x47CC16 | 0x468056 | build_hp_b | L2（纯重放化，见§4）未实测 |
| 12 | 冻结敌方2 | 0x30A5F6 | 8B48503B4E20 | 0x348A06 | 0x333886 | sidebar_pts | L2（纯重放化）未实测 |
| 13 | 缩放 | 0x1EC7CD | F30F114644 | 0x22B82D | 0x216C7D | power_cool | L2（ZF=OR 0x40 修复）方向未实测 |
| 14 | 地图全开 | 0x3C226C | F30F118560020000 | 0x4005BC | 0x3EB50C | unit_lv | L1（小地图全亮实测） |
| 15 | 无限弹药(UI写) | 0x128735 | 8B0CBA85C9 | 0x169D85 | 0x152115 | zoom_unit_xp | 被 weapon_clip 取代（见§3）弹药未实测 |
| 16 | 威胁等级 | 0x438ED0 | 8B8178120000 | 0x477090 等6处 | 0x4622E0 等6处 | ammo×6 | L2（v15 写50000/0/双关恢复）未实测 |
| 17 | 矿脉恢复 | 0x2D4933 | 8B40082B4114 | 0x312EB3 | 0x2FDBB3 | oremine | **v16 移植**（唯一命中+活体字节✓）效果未实测 |
| 18 | 敌方禁产 | 0x30F530 | 0350043BD7 | 0x34D920 | 0x3387D0 | 未挂钩 | **本轮定位**（唯一命中+活体字节✓）[eax+0xC]属主语义需活体验证后才能移植 |
| 19 | 无敌模式 | 0x12EEDF | 8B503C8BCE | 字节不存在 | 字节不存在 | 未挂钩 | 不可字节移植→可从 adjust 重设计（§5） |
| 20 | 一击必杀 | 0x3651AE | F30F114604 | adjust 0x3A366E | adjust 0x38CB4E | 未挂钩 | 同上（重推导点已活体确认字节） |
| 21 | OneKillData | 0x3FE714 | 8B8E3C030000 | 0x43C964 | 0x427B34 | 无需 | 被 adjust 重推导取代；候选 L3+活体字节✓ |
| 22 | OneKillData2 | 0x2E24E3 | 8B893C030000 | 0x320963 | 0x30B6C3 | 无需 | 同上（L4 候选） |

站点 18-22 均为本轮（2026-10-11）定位，工具：`tools/analysis/locate_final3_sites.py`。

## 2. FINAL3 游戏线程分派动作（iEnable+0x20 请求码）

资金结算桩在重放后消费请求槽 → MustCode+700 分派。RA3MT 对应实现：

| 码 | FINAL3 动作 | EA 实现 | RA3MT 现状 |
|---|---|---|---|
| 1 | 超高速 | Locomotor+8=500 | sel_speed，L2（500）未实测 |
| 2 | 低速 | =10 | sel_speed2，v15 对齐 10，L2 未实测 |
| 3 | 冻结 | =0 | sel_freeze，L2 未实测 |
| 4 | 恢复速度 | +0x40 备份回写 | sel_freeze2(speedrestore)，带状态备份 L2 |
| 5/6/7 | HP max/min/normal | +4/+C=9999999 / +4=1 / +10→+4,+C | sel_hpmax/hpmin/hpnormal(+heal)，L2 未实测 |
| 8 | 晋级 | call EA+35C200(0,1,3) | **晋级桥**（v15 接入，RA3MT_RANK_BRIDGE=1） |
| 9 | 改属主ID | [Body+418]=[ID] | sel_capture pending（禁止裸写，需完整归属切换） |
| A | 摧毁 | call EA+39EA50(0,19,6) | sel_destroy pending（需死亡回调/游戏线程） |
| B | 取我基地 | 鼠标坐标+造单位 | 未移植；已有严格 wrapper 解析器只解析 identity，不调用（安全 ABI/context/lifecycle/thread contract 未补齐） |
| C | WeNeedBack | 鼠标坐标+8单位循环 | 未移植；模板 hash/name 线索已确认，创建桥未验证 |
| D | 复制单位 | 模板字典 0x8E6C58 等价物 | 未移植；活体模板提取链已记录，但没有经过游戏线程的 spawn dispatcher |

## 3. FINAL3 对 Final2a 时代认知的误分类校正（含本轮新勘误）

1. **zoom/xp 站点（EA 0x128735）遍历的是 Weapon 而非选中单位**：条目+0x1C 是弹夹
   （FINAL3 标注 Select Unit Ammo）。Final2a 时代的 xp999 写 [entry+1C]=999 属于错误归类。
2. **旧 ammo 站点族（[ecx+0x1278]）是威胁等级访问器**（FINAL3 Danger Level），
   Final2a 时代误当无限弹药并写 [eax+8]=50000，实为威胁值。
3. **真选中列表**：root+0x50 哨兵链表 + Drawable↔Body 互指（FINAL3 GetUnitData 链），
   Final2a 时代的 [10a0c] TMK 槽/0x8E0940 全局判定均错。
4. **NormalHP = 撤销上限作弊**（+10 基准写回 +4/+C），不是治疗；v13 起区分 hpnormal/heal。
5. **协议点数=15、低速=10**：Final2a 转储里的 99/500 是误读。
6. **（本轮）NOTES 旧表"fast_build 0x312EB3/0x2FDBB3 瞬间完成生产"实为矿脉剩余量访问器**：
   位移字节 `8B40082B4114` 与 FINAL3 OreMine（EA 0x2D4933）完全一致，上下文为
   `[ecx+4]→[eax+8]-[ecx+14]` 剩余矿量计算。该站点从未被挂钩，现更名为 oremine（v16 已移植）。
7. **（本轮）无敌/一击必杀的字节序列在重打包中不存在**：EA 0x12EEDF/0x3651AE 不可字节移植；
   但 HP adjust 函数（1.13 RVA 0x38CB30 / 1.12 0x3A3650，双版本结构逐指令一致）内的
   血量写点 `movss [esi+4],xmm0`（0x38CB4E/0x3A366E）就是 OneKill 的语义等价位置，
   且 ecx-0x10=Body 可直接做属主判定——EA 的 OneKillData/Data2 三点捕获链不再需要。

## 4. EA 语义与 RA3MT 实现的有意差异

- **#11/#12（build_hp_b/sidebar_pts）**：EA 无属主判定地 +1 冻结所有记录（会误伤本地）。
  RA3MT 改为纯重放，冻结职责集中到带判定的 build_power/build_hp_a。属行为修正而非等价移植。
- **#17 矿脉**：EA 清零已采量是一次性自清标志；RA3MT 为持续回满（关闭后保留满量）。效果超集。
- **#4 协议点数**：EA 单次写 15；RA3MT 开关期间持续 15。
- **#15 弹药**：EA 在 UI 遍历点写 [Weapon+0x1C]=0x7FFFFFFF（不限属主/选中）；
  RA3MT 改挂在真实开火扣弹点（weapon_clip），按本地+选中位回填模板容量，不动连发计数。
  已空弹的武器需正常装填一次后生效（前置 guard 阻止空弹进入开火钩子）。
- **#2 资金**：EA 无上限（实测 int32 溢出事故）；RA3MT 加 1000 万封顶。

## 5. 不能安全移植 / 未实现清单（明确结论）

| 功能 | 结论 | 依据 |
|---|---|---|
| 俘虏 (#9) | **不可移植现方案**：裸写 Body+0x418 不走归属切换流程 | 归属切换函数已定位（1.13 RVA 0x3B5DF0，ECX=Body，arg1=+414 context，arg2 bool）但缺安全游戏线程队列；晋级桥模式验证后可复用 |
| 摧毁 (#A) | **不可移植现方案**：EA call EA+39EA50 的重打包对应未定位（无字节签名）；直接 HP+4=0 绕过死亡通知 0x7513F0 | v12 起禁用 |
| 敌方禁产 (#18) | **站点已定位未挂钩**：写 [eax+4]=5000/1 的语义明确，但 [eax+0xC] 属主字段在重打包中的表示（指针 vs 索引）未活体验证；误判会冻结己方生产 | EA 用 [ID+4]=[player+0x20] 比对；重打包等价锚待定 |
| 无敌 (#19) | **需重新设计**：站点字节不存在。可在 adjust 0x3A366E/0x38CB4E 前加属主判定桩（本地→写 +4/+8/+C=大值），未实现 | 本轮 adjust 结构双版本解析完成 |
| 一击必杀 (#20) | **需重新设计**：同上（非本地→强制 [esi+4]=0 走完整死亡流程），未实现 | 同上 |
| 取基地/WeNeedBack/复制 (#B/C/D) | **仍未移植**：1.13/1.12 startup hash lookup、四个 FINAL3 模板 hash 名称及 304B map-start wrapper identity 已经静态验证；但 owner/context 合同只有启动记录路径，位置只确认 engine-space，spawn 失败回滚/通用单位覆盖范围/游戏线程 mailbox 未实现。Free Build 玩家 permission branch 也未定位。 | `SpawnApiResolver` 仅严格解析 304B identity，不调用、不安装、不连接生产桥；`spawntest` 38 篡改拒绝；template hash verifier通过 |
| 瞬升三星 (旧[10]) | **pending**：直写字段不触发晋级；晋级桥（v15）实战稳定后由邮箱循环请求驱动 | 桥已离线全验证 |

## 6. 未实测功能清单（全部仅离线验证）

威胁等级×3、矿脉恢复、协议点数、解锁协议、立即就绪、冻结敌方、无限缩放（方向）、
无限弹药（weapon_clip）、全部选中类动作（速度/生命/恢复）、晋级桥（RA3MT_RANK_BRIDGE=1）。
已活体实测 ✓：无限资金（含封顶）、无限电力、快速建造、地图全开、44 挂钩字节（含 oremine 等
本轮 4 站点在运行进程中与文件字节一致）。

## 7. 验证证据索引

- 站点字节：SelfCheck 全量 44/44（双版本文件）+ 2026-10-11 运行中 1.13 进程只读比对
- 桩执行：`tools/harness/test_execution_stubs.py` 201 例（含威胁 48、矿脉 4）
- 晋级：`test_rank_dispatcher.py` 218、`test_rank_money_bridge.py` 8（端到端）、
  `tools/analysis/verify_final3_rank.py` 160（配对函数模拟执行）
- 引擎：actiontest 24 / installertest 138 / selectiontest 18 / rankmailboxtest 12 / asmtest 5
- 定位工具：`tools/analysis/locate_final3_sites.py`（可重复）
