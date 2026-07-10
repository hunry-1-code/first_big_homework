# 网络舆情事件智能分析系统 - 智能开发规则

## 核心开发记忆
1. **前端工程架构**：本项目前端已升级并重构为基于 **Vue Pure Admin** 模板的工程，位于工作区根目录的 [frontend/](file:///d:/work2/programing_practice_demo/frontend) 文件夹。
2. **状态与审计文档**：前端的所有已完成功能、待对齐需求、后端接口路径映射、Token 拦截机制以及 Windows 打包兼容性修复细节均被归档在工作区公共文档 [docs/frontend_changelog_and_memory.md](file:///d:/work2/programing_practice_demo/docs/frontend_changelog_and_memory.md) 中。

## AI 助手行为规则
* **优先阅读**：任何参与本项目开发、调试、新需求承接或新会话启动的 AI 助手，在开始研究和编写代码前，**必须强制读取并严格遵循 [docs/frontend_changelog_and_memory.md](file:///d:/work2/programing_practice_demo/docs/frontend_changelog_and_memory.md) 中的工程选型、路由拦截方式和接口映射逻辑**。
* **开发原则**：所有前端修改必须在现有的 Vue Pure Admin 风格体系内进行（即在原版布局和组件逻辑上做增删改，配合 Tailwind CSS / Element Plus 样式），禁止引入风格不一致或多余的 UI 样式库。
