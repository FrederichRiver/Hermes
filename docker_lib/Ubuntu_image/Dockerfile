FROM ubuntu:24.04

RUN mkdir /opt/application
RUN mkdir /opt/application/venv
RUN mkdir /opt/application/src
ENV DEBIAN_FRONTEND=noninteractive
ENV VIRTUAL_ENV=/opt/application/venv
ENV PATH="/opt/application/venv/bin:${PATH}"

RUN sed -i 's|http://archive.ubuntu.com/ubuntu/|http://mirrors.aliyun.com/ubuntu/|g' /etc/apt/sources.list.d/ubuntu.sources \
    && sed -i 's|http://security.ubuntu.com/ubuntu/|http://mirrors.aliyun.com/ubuntu/|g' /etc/apt/sources.list.d/ubuntu.sources

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv "$VIRTUAL_ENV"

WORKDIR /opt/application

CMD ["tail", "-f", "/dev/null"]
# CMD ["python3", "/opt/application/src/hermes", "start"]
