<p align="center">
  <img src="https://raw.githubusercontent.com/exfador/cxh-fp/v1.1/bot-profile/avatar.jpg" width="160" alt="CXH FP fox" />
</p>

# 🦊 CXH FP · Ubuntu installer

[![Installer checks](https://github.com/exfador/install-cxh-fp/actions/workflows/quality.yml/badge.svg?branch=main)](https://github.com/exfador/install-cxh-fp/actions/workflows/quality.yml)
[![CXH FP 1.1](https://img.shields.io/badge/CXH_FP-1.1-orange)](https://github.com/exfador/cxh-fp/releases/latest)

Установка [CXH FP](https://github.com/exfador/cxh-fp) на собственный сервер: выбор русского или английского языка, проверенный релиз, отдельный Python и служба systemd.

**Поддерживается Ubuntu 20.04, 22.04 и 24.04 LTS**, архитектуры x86_64 и aarch64. Нужны права sudo, работающий systemd, интерактивный терминал и доступ к Ubuntu, GitHub, python.org и PyPI. Первая сборка Python обычно занимает 10–20 минут; время зависит от сервера. Количество потоков ограничено доступной памятью.

Для новых серверов выбирайте Ubuntu 22.04 или 24.04. Для Ubuntu 20.04 расширенные обновления безопасности доступны через [Ubuntu Pro / ESM](https://ubuntu.com/security/esm); установщик не обновляет ОС автоматически.

## Установить

Скачайте файл, затем запустите его:

```bash
curl --fail --show-error --location --proto '=https' --tlsv1.2 https://raw.githubusercontent.com/exfador/install-cxh-fp/refs/heads/main/install_cxh_fp.sh -o cxh-fp-install.sh
bash cxh-fp-install.sh --preview --language ru
sudo bash cxh-fp-install.sh
```

Сначала выберите язык. Установщик покажет обнаруженную версию ОС и проверит совместимость. Если система не поддерживается, он явно сообщит причину и завершится без установки. Затем мастер запросит настройки FunPay и Telegram. Ключи вводятся в терминале без отображения. Служба включается после сохранения настроек.

Для проверки поддерживаемой системы без установки:

```bash
bash cxh-fp-install.sh --check --language en
```

Просмотр плана доступен на любой системе и ничего не меняет. Файл установщика также следует проверять перед запуском с sudo: скачивание по HTTPS не заменяет доверие к исходному коду.

## Что устанавливается

| Компонент | Расположение |
| --- | --- |
| CXH FP | `/opt/cxh-fp` |
| Python 3.11.16 | `/opt/cxh-python/3.11.16` |
| Виртуальное окружение | `/opt/cxh-fp/.venv` |
| Системный пользователь | `coxerhub`, без интерактивного входа |
| Домашняя папка | `/var/lib/cxh-fp` |
| Служба | `cxh-fp.service` |

Системный Python и глобальная локаль не меняются. PPA не добавляются, `get-pip.py` не скачивается и не запускается. Python собирается из исходников [официального выпуска 3.11.16](https://www.python.org/downloads/release/python-31116/); SHA-256 закреплён в установщике.

Релиз загружается из `exfador/cxh-fp`. Встроенный проверяющий код, системный Python и подписанный пакет Ubuntu `python3-cryptography` проверяют Ed25519-подпись закреплённым ключом, размер и SHA-256 архива, пути и типы ZIP-записей, точный список файлов и каждый хеш. Код проекта запускается только после проверки, от пользователя `coxerhub`. Зависимости устанавливаются из PyPI с закреплёнными версиями и хешами; готовые пакеты обязательны для всех зависимостей, кроме закреплённой `pyTelegramBotAPI 4.15.2`, доступной только исходным архивом. Её SHA-256 также проверяется; сборка выполняется от `coxerhub`, без автоматической загрузки дополнительных сборочных зависимостей.

Служба ограничена systemd: запрещено повышение прав, домашние каталоги закрыты, системные каталоги доступны только для чтения. Запись в папку проекта остаётся доступной для настроек, плагинов и подписанных обновлений. Плагины работают с правами бота: устанавливайте только доверенные.

## Повторный запуск и обновления

Повторный запуск сохраняет исходники, настройки, плагины, товары и журналы существующей установки в `/opt/cxh-fp`, восстанавливает зависимости, завершает отменённую настройку и перезапускает службу. Он не заменяет установленный код новым релизом. Обновляйте CXH FP в Telegram кнопкой **Обновления → Обновить**.

Существующие установки в других папках не переносятся и не удаляются. Для миграции предварительно остановите прежнего бота, сохраните резервную копию и перенесите совместимые настройки и данные отдельно. Одновременный запуск двух ботов с одним Telegram-токеном приводит к конфликту получения сообщений.

## Управление

```bash
sudo systemctl status cxh-fp
sudo systemctl restart cxh-fp
sudo systemctl stop cxh-fp
sudo journalctl -u cxh-fp -n 50
```

Установщик подтверждает готовность по маркеру текущего дочернего процесса, а не только по статусу systemd. Если подключение к FunPay или Telegram не установлено, он сообщает, что готовность не подтверждена. Данные сохраняются.

Канал проекта: https://t.me/funpay_coxerhub  
Основной канал: https://t.me/coxerhub

## Development

The readable verifier lives in `bootstrap/`; `installer.sh.in` contains the shell workflow, and `cxh-fp.service` contains the service configuration. `build.py` embeds the reviewed verifier and service into the single downloadable script without fetching unsigned helper code.

```bash
python3 build.py
bash -n install_cxh_fp.sh
python3 -m pytest tests -q
```

Tests use generated signing keys and isolated temporary directories. They cover tampering, ZIP traversal, symlinks, private paths, case collisions, compression bombs, malformed manifests, signature/key mismatches, existing-data preservation and interrupted installation. These checks do not replace an actual server installation test. CI checks the distro bootstrap verifier on Ubuntu 20.04, 22.04 and 24.04. The Ubuntu 20.04 container additionally builds Python 3.11.16, verifies and installs the signed release, installs hash-locked dependencies as the service user, checks runtime imports and setup commands, and validates the systemd unit. A container test does not verify service startup on a full VM or live FunPay/Telegram authentication.
