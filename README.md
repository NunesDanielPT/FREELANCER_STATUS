# Claquete
Organizador de eventos, clientes e faturas para freelancers de audiovisual (PC e telemóvel).
Não emite faturas: só controla datas, valores e estado (por faturar / faturada / paga).
Cada utilizador só vê os seus dados. Só biblioteca standard do Python + SQLite.

## Deploy no Portainer
Stacks > Add stack > Repository > URL deste repo, `docker-compose.yml`.
Usa a rede Docker já existente `networkpi` (tem de existir antes do deploy).
Variáveis de ambiente (todas opcionais, definem-se no Portainer, nunca no GitHub):

| Variável | Para quê |
|---|---|
| `BASE_URL` | Endereço do site, ex.: `http://192.168.0.47:8085`. Necessário para os links dos emails. |
| `SMTP_USER` | O teu Gmail usado só para enviar (ex.: `claquete.envio@gmail.com`). |
| `SMTP_PASSWORD` | "Palavra-passe de app" do Gmail (16 letras), não a palavra-passe normal. |
| `INVITE_CODE` | Código de convite inicial (depois muda-se no Admin). |
| `ADMIN_USER` | Opcional: utilizador que fica administrador. O primeiro registo já é admin. |

Emails enviados: boas-vindas no registo e link de recuperação de palavra-passe.
Sem `SMTP_USER`/`SMTP_PASSWORD`/`BASE_URL`, o link de recuperação aparece nos Logs do container.

## Gmail: palavra-passe de app
1. Na conta Gmail de envio, ativa a verificação em 2 passos.
2. Em https://myaccount.google.com/apppasswords cria uma palavra-passe de app (nome: Claquete).
3. Copia as 16 letras para `SMTP_PASSWORD` no Portainer.

## Backup
docker run --rm -v claquete_data:/data -v $PWD:/b alpine tar czf /b/backup.tgz -C /data .

## Admin
A primeira conta registada é administradora. Ícone **Admin** no menu: resumo e avisos, contas (editar email, repor password, suspender, apagar), nome/cores/textos do site, publicidade, backups (automático diário em `/data/backups`), restauro e consola SQL.
