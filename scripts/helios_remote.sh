# Production entry point appended to helios_release.sh and sent to sh -s over SSH.
if [ -d /usr/xpg4/bin ]; then PATH=/usr/xpg4/bin:$PATH; export PATH; fi
[ "$#" -eq 6 ] || die 'Expected action, root, account, channel, release, operation'
requested=$2; account=$3
case "$account" in s*) identifier "$account";; *) die 'Unexpected remote account';; esac
case "${account#s}" in ''|*[!0-9]*) die 'Unexpected remote account';; esac
[ "$(id -un)" = "$account" ] || die 'Unexpected remote account'
case "$requested" in
    /home/studs/"$account"/public_html/pyweb_lab1|/export/home/studs/"$account"/public_html/pyweb_lab1) ;;
    *) die 'Unexpected deployment root';;
esac
physical_home=$(cd -P "$HOME" && pwd -P)
case "$physical_home" in /home/studs/"$account"|/export/home/studs/"$account") ;;
    *) die 'Unexpected physical account home';;
esac
[ "$(cd -P "${requested%/public_html/pyweb_lab1}" && pwd -P)" = "$physical_home" ] || die 'Deployment root does not match account home'
command -v rsync >/dev/null || die 'rsync is not installed on Helios'
root=$physical_home/public_html/pyweb_lab1
state=$physical_home/.pyweb_lab1-deploy
run_action "$1" "$4" "$5" "$6"
