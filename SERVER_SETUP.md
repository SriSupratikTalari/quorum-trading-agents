# Deploying the upgrade on the AWS server

## 1. On your Mac
    python -m pytest tests -q
    git rm watcher.py
    git add . && git commit -m "Rules upgrade" && git push

## 2. On the server
    ssh -i ~/.ssh/quorum_keypair.pem ubuntu@3.144.19.168
    cd ~/quorum-trading-agents && git pull
    ~/miniforge3/envs/quorum/bin/python -m pip install pytest
    ~/miniforge3/envs/quorum/bin/python -m pytest tests -q

## 3. Replace the watcher service with the price guard
    sudo systemctl disable --now quorum-watcher
    sudo rm /etc/systemd/system/quorum-watcher.service
    sudo tee /etc/systemd/system/quorum-guard.service > /dev/null << 'UNIT'
    [Unit]
    Description=Quorum price guard
    After=network-online.target

    [Service]
    User=ubuntu
    WorkingDirectory=/home/ubuntu/quorum-trading-agents
    ExecStart=/home/ubuntu/miniforge3/envs/quorum/bin/python price_guard.py
    Environment=PYTHONUNBUFFERED=1
    Restart=always
    RestartSec=60

    [Install]
    WantedBy=multi-user.target
    UNIT
    sudo systemctl daemon-reload
    sudo systemctl enable --now quorum-guard
    sudo systemctl status quorum-guard --no-pager

## 4. Weekly report (Fridays 1:30pm Pacific)
    (crontab -l; echo "30 13 * * 5 cd /home/ubuntu/quorum-trading-agents && /home/ubuntu/miniforge3/envs/quorum/bin/python report.py >> /tmp/quorum-report.log 2>&1") | crontab -

## Everyday commands
    cat /tmp/quorum-daily.log                  # daily run
    journalctl -u quorum-guard -f              # price guard live
    cat data/trades.csv                        # every trade + practice action, with reasons
    cat data/state.json                        # peaks, stops, cooldowns, active/bench lists

## Emergency stop (no git needed)
    echo "TRADING_ENABLED=false" >> .env && sudo systemctl restart quorum-guard

## After a week of practice
Edit config.py on your Mac: set "practice": False for one rule, log it in CHANGELOG.md, push, pull, restart quorum-guard.