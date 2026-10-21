# Claquete
Organizador de eventos, clientes e faturas para freelancers de audiovisual (PC e telemóvel).
Não emite faturas: só controla datas, valores e estado (por faturar / faturada / paga).
Cada utilizador só vê os seus dados. Só biblioteca standard do Python + SQLite.

## Deploy no Portainer
Stacks > Add stack > Repository > URL deste repo, `docker-compose.yml`.
Todas as variáveis de ambiente são opcionais:

| Variável | Para quê |
|---|---|
| `INVITE_CODE` | Se definido, o registo exige este código (recomendado para só entrarem amigos). |
| `BASE_URL` | Endereço do site, ex.: `https://faturas.exemplo.pt`. Usado nos links de email. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | Envio de emails (recuperação de palavra-passe). Ex. Gmail: `smtp.gmail.com`, `587`, o teu email, uma "palavra-passe de app". |

Sem SMTP/BASE_URL, o link de recuperação aparece nos **Logs** do container (Portainer > Containers > organizador > Logs).

## Backup
docker run --rm -v organizador_data:/data -v $PWD:/b alpine tar czf /b/backup.tgz -C /data .
