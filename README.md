# Organizador de eventos e faturas
Site pessoal (PC e telemóvel) para controlar eventos, clientes e o estado de faturação/pagamento.
Não emite faturas. Só biblioteca standard do Python + SQLite.

## Deploy no Portainer
Stacks > Add stack > Repository > URL deste repo, ficheiro `docker-compose.yml`.
Abre o site: o primeiro registo cria a conta e o registo fecha depois.
Password perdida: define `RESET_USERS=1`, faz redeploy, regista-te de novo e remove a variável.

## Backup
docker run --rm -v organizador_data:/data -v $PWD:/b alpine tar czf /b/backup.tgz -C /data .
