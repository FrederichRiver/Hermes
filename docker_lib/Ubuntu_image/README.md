# Ubuntu 开发容器与多虚拟环境构建

本项目提供了一个基于 Ubuntu 24.04 (LTS) 的开发容器。考虑到您可能需要针对不同的应用（基础应用、AI 应用等）使用不同版本的 Python 和库，此架构采用了 **Conda** 环境隔离方案。

## 基础设施配置
- 基础系统：`ubuntu:24.04`
- 环境管理：`Miniconda3` (安装于 `/opt/conda`)。

## 虚拟环境说明
镜像构建过程中预设了两个基于 Conda 的隔离环境：

### 1. 基础应用环境 (`base_app`)
- **Python 版本**：`3.12`
- **目的**：用于常规应用开发或脚本运行。
- **使用方式**：进入容器后执行 `conda activate base_app`

### 2. AI 应用环境 (`ai_app`)
GT 720 (Kepler 架构，Compute Capability 3.5) 的限制比较苛刻。较新的 PyTorch (2.x) 和较高版本的 CUDA 已经移除了对 CC 3.5 的支持。
为了兼容这块显卡，环境做出了妥协：
- **Python 版本**：`3.9` (因为高版本 PyTorch 不兼容老卡，老版本 PyTorch 不兼容新版 Python)。
- **CUDA 版本**：`cudatoolkit 10.2`
- **PyTorch 版本**：`1.12.1`（此为最后一个预编译支持 CUDA 10.2 和老架构的 PyTorch 官方版本）。
- **使用方式**：进入容器后执行 `conda activate ai_app`

> **注意：** 要在容器里利用 GT 720 进行 CUDA 计算，您的宿主机必须已经安装了 NVIDIA 显卡驱动以及 [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)，且在 Windows (WSL2) / Linux 的底层环境中显卡能够正常被识别。

## 环境隔离与配置解耦
遵循配置解耦的原则，本项目将环境变量（如时区设置 `TZ=Asia/Shanghai` 或未来的 API Keys 等）从 `Dockerfile` 中剥离。
请在运行前复制环境变量映射文件：
```bash
cp .env.example .env
```
随后修改 `.env` 并在其中填入相关的属性。

## 启动指南

```bash
# 构建并后台启动开发容器
docker-compose up -d --build

# 进入容器的 bash
docker exec -it ubuntu_dev_env bash

# 在容器内切换所需的环境
# 比如激活 AI 环境：
conda activate ai_app
# 您可以验证此环境的 python 与 pytorch
python -c "import torch; print(torch.cuda.is_available())"
```

## 数据隔离约定
同样遵循解耦原则，所有的应用源码及项目资料可以直接放入本目录的 `workspace/` 中，它将直接映射为容器内的 `/workspace` 数据卷。