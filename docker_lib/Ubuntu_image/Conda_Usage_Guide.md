# Conda 环境配置与开发使用指南

本文档旨在介绍在当前 Ubuntu Docker 开发容器中，如何有效地配置、管理和使用 Conda 虚拟环境。

## 1. 现有环境概览
Docker 镜像内部以 Miniconda（安装于 `/opt/conda`）作为环境管理工具，并且预先构建了两个隔离的 Python 环境：
- **`base_app`**: Python 3.12（适用于日常爬虫、Web开发、普通业务脚本等常规应用）
- **`ai_app`**: Python 3.9 + PyTorch 1.12.1 + CUDA 10.2（由于您的显卡为 GT 720 / Kepler 架构，因此专门降配锁定的 AI 运行加速环境）

## 2. 基础操作与环境切换

在进入容器内部终端后（例如执行 `docker exec -it ubuntu_dev_env bash`），可以通过以下命令来管理当前环境：

### 查看所有已建立的环境
```bash
conda env list
```
*(带星号 `*` 的表示当前正在使用的环境目录)*

### 激活/进入指定环境
默认进入终端后通常位于基础 bash 或者 base 环境，如果你要使用具体的库，请先激活：
```bash
conda activate base_app
# 若进行 AI 计算则切换：
conda activate ai_app
```

### 退出当前虚拟环境
```bash
conda deactivate
```

## 3. 安装与管理依赖

在激活目标环境（如 `conda activate base_app`）的前提下，你可以灵活安装所需的开发框架或工具：

### 选用包管理工具 (Conda vs Pip)
*   **优先推荐 `conda install`**：它对底层的 C/C++ 依赖计算得更好，遇到复杂的科学计算库（NumPy, SciPy 等）或 AI 框架时更有优势。
    ```bash
    conda install pandas flask
    ```
*   **补充选用 `pip install`**：如果相应的包在 Conda 官方镜像通道中找不到最新版，请使用 pip 安装。
    ```bash
    pip install requests bs4
    ```

### 环境依赖导出与重建
为了让未来的团队成员或者生产环境能够 1:1 复现你当前的配置，请习惯在项目中保留环境配置表：
```bash
# 导出当前环境的依赖清单
conda env export > environment.yml

# 如果你想用别人的依赖清单来建立新环境
conda env create -f environment.yml
```

## 4. 创建自定义新环境

如果在未来的开发中有了需要诸如 Python 3.10 的特殊要求，可以直接在容器中新建：
```bash
# 创建一个名为 new_env 且指定 python 3.10 版本的环境
conda create -n new_env python=3.10

# 删除一个不再需要的废弃环境
conda env remove -n new_env
```

## 5. 配合 VS Code ( IDE ) 的完美实践

如果您使用 VS Code 进行主力开发，极度推荐使用 Remote - Containers (Dev Containers) 插件直接附加 (Attach) 到运行中的这个 `ubuntu_dev_env` 容器中。

1. **附加到容器**：通过 VS Code 左下角的远程连接标志，选择 "Attach to Running Container..." 并选择本容器。
2. **打开代码目录**：进入容器后，用 VS Code 打开挂载在项目根目录的 `/workspace` 数据卷。
3. **精准选择 Python 解释器**：按快捷键 `Ctrl+Shift+P`，搜索并执行 **`Python: Select Interpreter`**。你可以直接在列表中看到 Conda 为你创建的 `base_app` 和 `ai_app`，请根据当前开发项目选择对应的那个。
4. **效果**：完成选择后，VS Code 打开的内置集成终端会自动帮你 `conda activate` 对应环境；代码的智能提示、跳转以及执行器，也都将精确基于该隔离环境解析，避免因为包版本冲突导致的开发烦恼。

---
> **最后提示 (极其重要)**：
> 手动通过终端 `conda install` 在容器里安装的包只要容器不被销毁就会一直存在；但如果执行了 `docker-compose down` 并携带了卷删除，或者 `--build` 重新构建过镜像，您手动敲命令安装的包可能丢失。 **最佳实践是验证好配置后，将固定的包追加写入到 `Dockerfile` 中的 `RUN conda install ...` 命令里，或使用 `environment.yml` 跟随你的代码一起放入 `/workspace` 中持久化记录。**