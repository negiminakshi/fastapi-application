#!/bin/bash

TIMESTAMP=$(date +%F-%H-%M)

docker exec db pg_dump -U app appdb > ~/backups/backup-$TIMESTAMP.sql
