FROM python:3.14-slim

WORKDIR /app

COPY requirements.txt .
# Debian trixie 使用 DEB822（debian.sources）；兼容旧版 sources.list
RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g; s|security.debian.org|mirrors.tuna.tsinghua.edu.cn|g' \
        /etc/apt/sources.list.d/debian.sources; \
    fi; \
    if [ -f /etc/apt/sources.list ]; then \
      sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g; s|security.debian.org|mirrors.tuna.tsinghua.edu.cn|g' \
        /etc/apt/sources.list; \
    fi; \
    apt-get update \
    && apt-get install -y --no-install-recommends fontconfig fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

COPY app ./app

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
