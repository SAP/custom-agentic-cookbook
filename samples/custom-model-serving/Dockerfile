# syntax=docker/dockerfile:1@sha256:4edf897a3ffa55b89f906fc8cc78afdb3f1834cc9c7083565e611a8a7d5fe99e
FROM --platform=$BUILDPLATFORM python:3.12.16-alpine3.24@sha256:5789aa194f757888f41fa3d48e14b6feaa1b57c0af0b56fcb1372d6474d3bff0 AS model
COPY download_model.py /download_model.py
COPY qwen2.5-1.5b-manifest.json /qwen2.5-1.5b-manifest.json
RUN --mount=type=cache,id=cookbook-qwen-model-blobs,target=/download-cache \
    python -c 'from pathlib import Path; from download_model import install; install(Path("/download-cache"))' \
    && cp -a /download-cache /models
FROM alpine:3.23.4@sha256:5b10f432ef3da1b8d4c7eb6c487f2f5a8f096bc91145e68878dd4a5019afde11 AS build
RUN apk upgrade --no-cache && apk add --no-cache g++ cmake ninja linux-headers
ADD --checksum=sha256:dbaf04129434d26ef902b6bd521de2d25637b2a12aadbbe35fc9216438a60e01 https://api.github.com/repos/ggml-org/llama.cpp/tarball/8642541b255bfb5dc39cd351a178be09013a55d6 /tmp/llama.tar.gz
RUN mkdir /source && tar -xzf /tmp/llama.tar.gz --strip-components=1 -C /source
RUN cmake -S /source -B /build -G Ninja -DCMAKE_BUILD_TYPE=Release -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_APP=OFF -DLLAMA_BUILD_UI=OFF -DLLAMA_USE_PREBUILT_UI=OFF -DLLAMA_SUBPROCESS=OFF -DLLAMA_OPENSSL=OFF -DBUILD_SHARED_LIBS=OFF -DGGML_OPENMP=OFF -DGGML_NATIVE=OFF -DGGML_CPU_ALL_VARIANTS=OFF \
    && cmake --build /build --target llama-server -j 4
FROM alpine:3.23.4@sha256:5b10f432ef3da1b8d4c7eb6c487f2f5a8f096bc91145e68878dd4a5019afde11
RUN apk upgrade --no-cache && apk add --no-cache libstdc++
COPY --from=build /build/bin/llama-server /usr/local/bin/llama-server
COPY --from=build /source/LICENSE /licenses/llama.cpp-MIT
COPY --from=model /models/blobs/sha256-183715c435899236895da3869489cc30ac241476b4971a20285b1a462818a5b4 /models/qwen2.5-1.5b.gguf
COPY --from=model /models/blobs/sha256-832dd9e00a68dd83b3c3fb9f5588dad7dcf337a0db50f7d9483f310cd292e92e /licenses/Qwen-Apache-2.0
LABEL org.opencontainers.image.upstream.revision="8642541b255bfb5dc39cd351a178be09013a55d6"
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/llama-server"]
CMD ["--model", "/models/qwen2.5-1.5b.gguf", "--alias", "qwen2.5:1.5b", "--host", "0.0.0.0", "--port", "8080", "--ctx-size", "4096", "--parallel", "1", "--threads", "4", "--n-predict", "192", "--no-webui"]
