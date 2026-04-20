FROM mcr.microsoft.com/devcontainers/base:debian

# Rename vscode user to dev (base image has vscode with UID 1000)
RUN usermod -l dev -d /home/dev -m vscode \
    && groupmod -n dev vscode \
    && sed -i 's/vscode/dev/g' /etc/sudoers.d/vscode || true \
    && mv /etc/sudoers.d/vscode /etc/sudoers.d/dev 2>/dev/null || true

# Remove unused zsh/oh-my-zsh (~15MB)
RUN rm -rf /home/*/.oh-my-zsh /root/.oh-my-zsh && apt-get purge -y zsh && apt-get autoremove -y

# Install Python and development dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set Python path
ENV PATH="/home/dev/.local/bin:${PATH}"

# SSH quiet config
RUN mkdir -p /home/dev/.ssh \
    && printf 'Host *\n    StrictHostKeyChecking accept-new\n    LogLevel ERROR\n' > /home/dev/.ssh/config \
    && chmod 700 /home/dev/.ssh \
    && chmod 600 /home/dev/.ssh/config \
    && chown -R dev:dev /home/dev/.ssh

# Auto-cd to workspace for SSH sessions
RUN echo 'cd /workspaces/Universal-Embedded-Workbench 2>/dev/null' >> /home/dev/.bashrc

USER dev
