#!/usr/bin/env bash
# 下载预设背景图到 nonebot_plugin_custom_news/assets/backgrounds/
set -u
cd "$(dirname "$0")/../nonebot_plugin_custom_news/assets/backgrounds" || exit 1

declare -A JOBS=(
  [starry]="starry%20night%20sky%20over%20quiet%20mountains%2C%20deep%20blue%20purple%20galaxy%2C%20milky%20way%2C%20soft%20glow%2C%20anime%20landscape%20illustration%2C%20no%20text%2C%20no%20people:77"
  [ocean]="bright%20blue%20sky%20with%20white%20clouds%20over%20calm%20ocean%2C%20fresh%20cyan%20and%20azure%20gradient%2C%20summer%20breeze%2C%20clean%20anime%20style%20illustration%2C%20no%20text%2C%20no%20people:108"
  [dusk]="warm%20sunset%20golden%20hour%2C%20orange%20and%20amber%20sky%20with%20soft%20clouds%2C%20city%20silhouette%2C%20cozy%20evening%20glow%2C%20anime%20illustration%2C%20no%20text%2C%20no%20people:233"
  [mint]="fresh%20mint%20green%20rolling%20hills%20with%20soft%20morning%20mist%2C%20pastel%20teal%20and%20white%2C%20peaceful%20nature%2C%20clean%20anime%20illustration%2C%20no%20text%2C%20no%20people:55"
  [ink]="minimal%20light%20gray%20white%20abstract%20background%2C%20soft%20paper%20texture%2C%20subtle%20geometric%20lines%2C%20clean%20modern%2C%20elegant%20simplicity%2C%20no%20text:89"
)

for name in "${!JOBS[@]}"; do
  IFS=':' read -r prompt seed <<< "${JOBS[$name]}"
  curl -sL --retry 3 --max-time 300 \
    "https://image.pollinations.ai/prompt/${prompt}?width=1080&height=1620&nologo=true&seed=${seed}&model=flux" \
    -o "${name}.jpg" &
done
wait
ls -la
