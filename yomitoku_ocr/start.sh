#!/bin/bash

# Start cron service
service cron start

# Start Flask application
exec python main.py --server
