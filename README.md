# Hermes 项目文档组织与维护指南

## 目录结构建议

```text
.config/                     # kimi code工作相关的配置文件，包括skill的存放
.github/                     # vscode copilot工作相关的文件.
.venv/                       # Python虚拟环境目录
.vscode/                     # VSCode相关配置文件
dist/                        # 存放构建生成的分发文件
docker_lib/                  # 存放与Docker相关的配置和脚本
docs/                        # 存放系统文档和功能设计文件以及辅助资料
├── CDD-xxxx.md              # class definition document, 用于记录类的定义、属性和方法等信息
├── RD-xxxx.md               # Reference document, 用于记录参考资料、文献等信息
tests/                       # 存放测试代码和测试结果
webui/                       # 存放Web用户界面代码文件
.gitignore                   # Git忽略文件配置
AGENTS.md                    # 记录各Agent/模块的功能、接口、协作方式等信息
package_versions.txt          # 记录各个包的版本信息
```

## 维护建议

- 每次设计或实现有重大调整时，及时同步更新相关文档。
- 文档内容建议使用Markdown格式，便于版本管理和协作。
- 目录结构和命名保持简洁、统一，便于长期维护。
- 重要决策、约束、TODO等可用专门小节或标签标注。

---
