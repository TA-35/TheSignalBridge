#!/bin/bash
# Run once on the AWS inference box (Amazon Linux 2023), as ec2-user:
#
#     bash aws_tunnel_endpoint.sh
#
# Compose runs on the uni GPU server (the classifiers, the model and the
# grounding check), which can't take inbound connections and can only connect
# out on a few ports (443 among them). So it dials out to this box on 443 and
# forwards 127.0.0.1:18100 here to its own Compose service. This box's
# inference service hands Compose requests to it through
# COMPOSE_REMOTE_URL=http://127.0.0.1:18100 (in ~/inference/.env).
#
# The tunnel user has no shell, and its key can do exactly one thing: listen
# on 127.0.0.1:18100 on this box. It can't run commands, open a terminal, or
# reach anything else here or in the VPC. SSH on port 22 is left as it is.
# Safe to run again.
set -euo pipefail

TUNNEL_KEY='ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINki/EVNx/9EhKBQroOhcw7fHTbTTuBTcY2HIuqx43ed uni-gpu-llm-tunnel'
LISTEN='127.0.0.1:18100'

id llmtunnel >/dev/null 2>&1 || sudo useradd --create-home --shell /sbin/nologin llmtunnel
sudo install -d -m 700 -o llmtunnel -g llmtunnel /home/llmtunnel/.ssh
echo "restrict,port-forwarding,permitlisten=\"$LISTEN\" $TUNNEL_KEY" \
  | sudo tee /home/llmtunnel/.ssh/authorized_keys >/dev/null
sudo chown llmtunnel:llmtunnel /home/llmtunnel/.ssh/authorized_keys
sudo chmod 600 /home/llmtunnel/.ssh/authorized_keys

# sshd also listens on 443. Once any Port line exists sshd stops adding the
# default 22, so name 22 too - unless the main config already does.
PORTS='Port 443'
sudo grep -qE '^\s*Port\s' /etc/ssh/sshd_config || PORTS=$'Port 22\nPort 443'
sudo tee /etc/ssh/sshd_config.d/50-llm-tunnel.conf >/dev/null <<EOF
$PORTS

Match User llmtunnel
    AllowTcpForwarding remote
    PermitListen $LISTEN
    PermitOpen none
    PermitTTY no
    X11Forwarding no
    AllowAgentForwarding no
    ForceCommand /bin/false

# Close the Match block. Without this, every setting that comes after this
# file in sshd_config would apply to llmtunnel only.
Match all
EOF

# SELinux is permissive on Amazon Linux 2023 by default; if it's enforcing,
# sshd needs leave to bind 443.
if command -v getenforce >/dev/null && [ "$(getenforce)" = "Enforcing" ]; then
  sudo semanage port -a -t ssh_port_t -p tcp 443 2>/dev/null || sudo semanage port -m -t ssh_port_t -p tcp 443
fi

sudo sshd -t                     # stop on a config error, before the running sshd is touched
sudo systemctl reload sshd
sleep 1
echo "sshd is listening on:"
sudo ss -ltnp | awk '/sshd/ {print "  " $4}'
