#! /bin/sh

cd /opt/cloudplow
git pull
rm -rf locks

if [ ! -f ${CLOUDPLOW_CONFIG} ]
then
    python3 /opt/cloudplow/cloudplow.py run
    echo "Default config.json generated, please configure for your environment. Exiting."
elif grep -qP "\"rclone_config_path\":\s*\"/home/(seed|user)/\.config/rclone/rclone\.conf\"" ${CLOUDPLOW_CONFIG}
then
    echo "config.json has not been configured, exiting."
    echo "Along with configuring other settings, rclone_config_path needs to point to /config/rclone/rclone.conf due to the rclone base image's expectations."
elif grep -qP "\"rclone_config_path\":\s*\"/config/rclone/rclone\.conf\"" ${CLOUDPLOW_CONFIG}
then
    python3 /opt/cloudplow/cloudplow.py run
fi

