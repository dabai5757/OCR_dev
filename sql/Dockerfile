FROM mysql:8.0

COPY init.sql /docker-entrypoint-initdb.d/

COPY my_dev.cnf /etc/mysql/my.cnf

RUN chmod 644 /etc/mysql/my.cnf