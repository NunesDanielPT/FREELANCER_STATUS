# Organizador de eventos e faturas
Site pessoal (PC e telemóvel) para controlar eventos, clientes e o estado de faturação/pagamento.
Não emite faturas. Só biblioteca standard do Python + SQLite.

## Deploy no Portainer
Stacks > Add stack > Repository > URL deste repo, ficheiro `docker-compose.yml`.
Em Environment variables: `ADMIN_USER` e `ADMIN_PASSWORD` (só usadas na 1.ª execução).

## Backup
docker run --rm -v organizador_data:/data -v $PWD:/b alpine tar czf /b/backup.tgz -C /data .
