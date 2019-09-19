FROM rclone/rclone:beta
MAINTAINER sabrsorensen@gmail.com

# linking the base image's rclone binary to the path expected by cloudplow's default config
RUN ln /usr/local/bin/rclone /usr/bin/rclone

WORKDIR /

# install dependencies for cloudplow and start script, upgrade pip
RUN apk -U add coreutils git python3 py3-pip grep && \
    python3 -m pip install --upgrade pip

# configure environment variables to keep the start script clean
ENV CLOUDPLOW_CONFIG /config/config.json
ENV CLOUDPLOW_LOGFILE /config/cloudplow.log
ENV CLOUDPLOW_LOGLEVEL DEBUG
ENV CLOUDPLOW_CACHEFILE /config/cache.db

ADD . /opt/cloudplow

RUN cd /opt/cloudplow && \
    # install pip requirements
    python3 -m pip install --no-cache-dir -r requirements.txt

ADD docker-utils/start-cloudplow.sh /
RUN chmod +x /start-cloudplow.sh

# map /config to host defined config path (used to store configuration from app)
VOLUME /config

ENTRYPOINT ["/bin/sh", "/start-cloudplow.sh"]
