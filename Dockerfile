FROM rclone/rclone
MAINTAINER l3uddz@gmail.com

ARG BUILD_DATE
ARG VCS_REF

LABEL org.label-schema.vcs-ref=$VCS_REF \
      org.label-schema.vcs-url="https://github.com/l3uddz/cloudplow.git" \
      org.label-schema.build-date=$BUILD_DATE

# linking the base image's rclone binary to the path expected by cloudplow's default config
RUN ln /usr/local/bin/rclone /usr/bin/rclone

WORKDIR /

# install dependencies for cloudplow and user management, upgrade pip
RUN apk -U add --no-cache \
        coreutils \
        findutils \
        git \
        grep \
        py3-pip \
        python3 \
        shadow \
        tzdata && \
        python3 -m pip install --upgrade pip

# install s6-overlay for process management
ADD https://github.com/just-containers/s6-overlay/releases/download/v1.22.1.0/s6-overlay-amd64.tar.gz /tmp/
RUN tar xzf /tmp/s6-overlay-amd64.tar.gz -C /

# add s6-overlay scripts and config
ADD docker-utils/root/ /

# create cloudplow user
RUN useradd -U -r -m -s /bin/false cloudplow

# configure environment variables to keep the start script clean
ENV CLOUDPLOW_CONFIG /config/config.json
ENV CLOUDPLOW_LOGFILE /config/cloudplow.log
ENV CLOUDPLOW_LOGLEVEL DEBUG
ENV CLOUDPLOW_CACHEFILE /config/cache.db

ADD . /opt/cloudplow

RUN cd /opt/cloudplow && \
    # install pip requirements
    python3 -m pip install --no-cache-dir -r requirements.txt

# map /config to host defined config path (used to store configuration from app)
VOLUME /config

# map /data to media queued for upload
VOLUME /data

ENTRYPOINT ["/init"]
