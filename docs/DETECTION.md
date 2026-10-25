# RA3MT 公开进程识别协议

从 **v261025-8** 开始，官方修改器公开一个固定项目身份，供联机对战平台识别并执行自己的准入规则。它同时覆盖修改器进程和已经进入注入安装阶段的游戏进程，适用于本项目支持的全部六个游戏构建。

这是主动配合检测的公开标记，不是密码学签名。第三方可以移除、伪造或复制它；旧版本也没有这个标记。未检出不能证明游戏未被修改，检出也不等于某项功能正在启用。平台应结合自己的检测结果制定规则。

## 永久身份

项目 ID 永久固定，不随日期版本、编译结果、文件改名、游戏产品或构建变化：

```text
2A616556-4683-43AF-8863-359BF95B0FEE
```

内存记录的前 32 字节永久固定，可作为搜索特征：

```text
52 41 33 4D 54 2D 49 44 45 4E 54 49 54 59 00 00
2A 61 65 56 46 83 43 AF 88 63 35 9B F9 5B 0F EE
```

前 16 字节是 ASCII `RA3MT-IDENTITY` 加两个零字节；后 16 字节按 GUID 字符串去掉连字符后的顺序编码，**不是 .NET `Guid.ToByteArray()` 的混合端序**。记录地址、PID 和校验值会变化，不能把整个 64 字节当作固定签名。

## 修改器进程

修改器在 WPF 启动阶段创建以下两项，持有到进程退出：

1. 一份非托管、可读的 64 字节身份记录，类型为 `1`。
2. 一个不申请所有权、不执行等待的命名互斥对象，名字为：

```text
Local\RA3MT.Identity.2A616556-4683-43AF-8863-359BF95B0FEE.<十进制 PID>
```

例如 PID 为 `1234` 时，末尾是 `.1234`。平台可枚举同一 Windows 会话中的进程，按 PID 组装名字，用 `OpenMutexW(SYNCHRONIZE, FALSE, name)` 探测并立即 `CloseHandle`，不需要取得互斥锁。`Local\` 是会话范围；跨会话服务需要在对应会话探测，或改用进程内存/镜像识别。API 失败时区分不存在、权限不足及其他错误，不能一律算作没有标记。[OpenMutexW 文档](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-openmutexw)

平台应及时关闭自己的探测句柄。Windows 在最后一个句柄关闭时删除对象；长期持有探测句柄会使对象在修改器退出后仍然存在。互斥对象可被其他进程创建，适合作为发现线索；需要关联具体进程时，再校验该进程的完整内存记录和 PID。

发布 exe 的原生 `RT_MANIFEST` 资源还包含固定的应用身份：

```text
RA3MT.Trainer.2A616556-4683-43AF-8863-359BF95B0FEE
```

该值是 XML `assemblyIdentity/@name`，不会随发布文件名和版本改变。平台读取进程镜像文件时，可解析原生 PE 清单资源；无需依赖压缩的 .NET 单文件包内容或某个固定文件偏移。清单身份用于识别文件，不能单独证明某个游戏进程曾被附加。[应用清单文档](https://learn.microsoft.com/en-us/windows/win32/sbscs/application-manifests)

## 游戏进程

游戏标记位于注入块的独立保留区：当前为 `MasterCode` 的 8 KiB 分配块末尾 `+0x1FC0`，长度 64 字节，类型为 `2`。初始块写入同时发布标记，发生在安装第一个游戏挂钩之前。地址随每次分配变化，平台应搜索固定前缀并解析记录，不应依赖该内部布局永远不变。

- 不修改磁盘上的游戏 exe 或 `.game` 文件。
- 普通脱离、关闭所有功能、修改器退出及挂钩恢复不会清除已完整写入的标记；它随游戏进程结束而消失。
- 完整写入初始块后，即使后续安装失败并回滚，也会保留标记。判别阶段就拒绝附加、分配失败或初始写入不完整时，不保证留下有效记录。
- 重复附加可能留下多份有效记录，按游戏 PID 去重即可。
- 标记表达“该游戏进程曾进入 RA3MT 注入安装阶段”，不表达当前是否附加、是否启用作弊，或游戏状态是否已经恢复。

## 64 字节记录，协议版本 1

所有整数均为无符号 32 位、小端序；GUID 仍按前文的固定字节顺序。

| 偏移 | 长度 | 内容 |
|---|---:|---|
| `0x00` | 16 | `RA3MT-IDENTITY` + 两个零字节 |
| `0x10` | 16 | 永久项目 GUID 的规范顺序字节 |
| `0x20` | 4 | 协议版本，固定 `1` |
| `0x24` | 4 | 记录长度，固定 `64` |
| `0x28` | 4 | 类型：`1` 修改器，`2` 游戏 |
| `0x2C` | 4 | 记录所在进程的 PID |
| `0x30` | 4 | 创建记录的修改器 PID |
| `0x34` | 4 | 保留，必须为零 |
| `0x38` | 4 | 保留，必须为零 |
| `0x3C` | 4 | 前 60 字节的 FNV-1a 32 位校验 |

FNV-1a 初始值为 `2166136261`，逐字节计算 `hash = (hash XOR byte) * 16777619`，按 32 位无符号整数溢出截断。校验只用于发现损坏或误命中，不能用于认证来源。

检测时必须校验前缀、协议、长度、类型、两个保留字段和校验值，并确认 `0x2C` 的 PID 等于正在读取的进程 PID。修改器类型还应满足 `0x30 == 0x2C`。游戏记录的创建者进程可能已经退出，或 PID 已被其他进程复用，因此不能要求创建者仍然运行，也不能只靠创建者 PID 关联其当前身份。

平台只需读取目标内存。可用 `VirtualQueryEx` 枚举已提交、可读的 `MEM_PRIVATE` 区域，跳过 `PAGE_GUARD`/`PAGE_NOACCESS`，包含可读写及可执行读写区域，再用 `ReadProcessMemory` 分块搜索。分块间保留 63 字节重叠，或在找到前缀后单独读取完整记录，避免漏掉跨块记录。读取失败、短读、进程退出或权限不足应作为“无法判定”处理。所需权限包括 `PROCESS_QUERY_INFORMATION` 和 `PROCESS_VM_READ`。[ReadProcessMemory 文档](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-readprocessmemory)

Core 已提供解析方法，可用于平台自己的检测实现：

```csharp
// candidate：从目标进程读到的完整 64 字节；observedPid：目标进程 PID。
if (TrainerIdentity.TryParse(candidate, out var record) &&
    record.OwnerProcessId == observedPid &&
    (record.Kind != TrainerIdentityKind.TrainerProcess ||
     record.TrainerProcessId == record.OwnerProcessId))
{
    // 按 record.Kind 区分修改器或被附加的游戏，再应用平台准入规则。
}
```

## 实现与验证

- `Model/TrainerIdentity.cs`：固定常量、记录编码、校验与解析。
- `Platform/TrainerProcessIdentity.cs`：修改器内存记录和命名对象生命周期。
- `Engine/BlockLayoutCatalog.cs`、`MasterCode.cs`：游戏标记保留区与初始发布。
- `UI/App.xaml.cs`、`app.manifest`：启动时创建标记、退出释放及原生文件清单。
- `SelfCheck identitytest`：157 项检查，包括永久常量、标准 FNV 向量、格式/损坏拒绝、布局和清单一致性，以及自建子进程的真实跨进程读取、命名对象发现和退出清理；不访问游戏。
- 安装失败/恢复检查及三个起义构建的模拟安装检查，验证游戏标记不会被脱离或已完整写入后的回滚擦除。

公开协议只负责提供稳定识别入口。尚未接入或实测任何第三方对战平台的封锁流程。
