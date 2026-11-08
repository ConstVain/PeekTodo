# PeekTodo 源码阅读路线

建议先启动一次面板，再按下面的顺序读。项目使用同一套业务规则服务桌面面板和命令行诊断。

| 目录或入口 | 职责 |
|---|---|
| `app.py` | 选择命令行或桌面入口，检查单实例，装配桌面控制器。 |
| `ui/` | 接收 Qt 事件，显示任务和刷新状态，提供设置窗口。主题和字体也留在这一层。 |
| `application/` | 把配置转换成数据源和映射规则，编排一次刷新或勾选操作。 |
| `domain/` | 定义文档树和任务，解释时间标题，生成三种模式的面板内容，计算贴边判定。 |
| `sources/` | 把 Markdown 和幕布缓存读成统一的文档树。 |
| `storage/` | 读取配置，保存本地勾选，确定配置和状态文件的位置。 |
| `windows/` | 实现快捷方式、自启、单实例锁和窗口焦点等 Windows 集成。 |

## 从一次刷新读起

1. 打开 [app.py](../peek_todo/app.py)，找到桌面入口创建的 `DesktopController`。然后读 [desktop.py](../peek_todo/ui/desktop.py) 的 `refresh`，它接收托盘和定时器的请求。
2. 看 [session.py](../peek_todo/application/session.py) 的 `TaskSession.refresh`。数据源返回 `Node` 树，[structure.py](../peek_todo/domain/structure.py) 按选中的根和模式生成任务分组，[selection.py](../peek_todo/domain/selection.py) 再按当前时间生成面板内容。
3. 回到 [panel.py](../peek_todo/ui/panel.py) 的 `present`。任务变化才重建任务行，状态提示可以独立更新。一次读取失败时会保留上次可用的任务内容，恢复成功后，即使任务没变，状态也会更新。

## 从一次勾选读起

1. [panel.py](../peek_todo/ui/panel.py) 的 `TaskRow` 发出任务 ID 和目标完成状态。上方、下方和未识别时间区走同一条路径。
2. `DesktopController.on_toggle` 把请求交给 `TaskSession.set_done`。[state.py](../peek_todo/storage/state.py) 把勾选原子写入共享状态文件。下一次刷新会用本地值覆盖源文档里的完成状态。
3. 查看 [markdown.py](../peek_todo/sources/markdown.py) 的节点标识。文件路径、父节点和任务文本帮助程序在插行或重排时识别原任务。改写任务标题或移到另一个分组会改变标识。同一父节点下完全同名的条目按出现顺序区分。

想从命令行看同一套解析规则，可运行 `python -m peek_todo --doctor --config config.example.json`。想确认启动入口和文件位置，可运行 `python -m peek_todo --where`。主要回归用例在 [tests](../tests)。
