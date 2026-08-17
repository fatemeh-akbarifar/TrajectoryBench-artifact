FROM r-base@sha256:05ead76278095fb3c9a68509714f843a80c296db7c31f3a0a890c51d263ea43d

RUN apt-get update \
    && apt-get install -y --no-install-recommends r-cran-jsonlite r-cran-lme4 \
    && rm -rf /var/lib/apt/lists/*
