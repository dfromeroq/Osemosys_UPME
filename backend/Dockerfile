FROM python:3.13-slim

ARG HIGHS_BUILD_FROM_SOURCE=0
ARG HIGHS_GIT_REF=master
ARG HIGHS_ENABLE_HIPO=0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && if [ "${HIGHS_BUILD_FROM_SOURCE}" = "1" ]; then \
        apt-get install -y --no-install-recommends \
          build-essential \
          ca-certificates \
          cmake \
          git \
          glpk-utils \
          libopenblas-dev; \
      else \
        apt-get install -y --no-install-recommends \
          ca-certificates \
          glpk-utils; \
      fi \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN if [ "${HIGHS_BUILD_FROM_SOURCE}" = "1" ]; then \
      grep -v '^highspy' /app/requirements.txt > /tmp/requirements-no-highspy.txt; \
      pip install --no-cache-dir -r /tmp/requirements-no-highspy.txt; \
      git clone --depth 1 --branch "${HIGHS_GIT_REF}" https://github.com/ERGO-Code/HiGHS.git /tmp/HiGHS; \
      if [ "${HIGHS_ENABLE_HIPO}" = "1" ]; then \
        export CMAKE_ARGS="-DFAST_BUILD=ON -DHIPO=ON"; \
      else \
        export CMAKE_ARGS="-DFAST_BUILD=ON"; \
      fi; \
      pip install --no-cache-dir /tmp/HiGHS; \
      rm -rf /tmp/HiGHS /tmp/requirements-no-highspy.txt; \
    else \
      pip install --no-cache-dir -r /app/requirements.txt; \
    fi

COPY . /app

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
