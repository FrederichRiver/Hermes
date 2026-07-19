FROM ubuntu:24.04

# 避免交互式提示
ENV DEBIAN_FRONTEND=noninteractive

# 安装基础依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    curl \
    git \
    build-essential \
    tzdata \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 设置时区
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 设置 Miniconda 来管理不同的 Python 虚拟环境
# 安装 Miniconda 可以方便地创建带有不同 Python 版本的独立环境
RUN wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O miniconda.sh && \
    bash miniconda.sh -b -p /opt/conda && \
    rm miniconda.sh

ENV PATH="/opt/conda/bin:$PATH"

# ---- 环境构建 ----

# 1. 创建基础应用环境 (Python 3.12)
RUN conda create -y -n base_app python=3.12 && \
    conda clean -ya

# 2. 创建 AI 应用环境
# 由于您的显卡为 GT 720 (Kepler 架构，Compute Capability 3.5)
# 较新的 PyTorch 和 CUDA 不再支持 Compute Capability 3.5。
# 最后一个官方预编译支持 CUDA 10.2 (支持 CC 3.5) 的 PyTorch 版本通常是 1.12.1。
# 若要在该卡上跑 PyTorch CUDA，您可能需要安装较低版本的 Python (如 3.8/3.9)，因为 PyTorch 1.12.1 不支持 Python 3.12。
RUN conda create -y -n ai_app python=3.9 && \
    # 使用 conda 激活环境并安装 pytorch 1.12.1 和 cudatoolkit 10.2
    /bin/bash -c "source activate ai_app && conda install -y pytorch==1.12.1 torchvision==0.13.1 torchaudio==0.12.1 cudatoolkit=10.2 -c pytorch" && \
    conda clean -ya

# 初始化 conda bash
RUN conda init bash

# 工作目录
WORKDIR /workspace

# 默认进入 bash
CMD ["/bin/bash"]
