# POSIX shell release store. Loaded via SSH stdin, not executed on the runner.
# Paths root/state are set by the validated entry point (helios_remote.sh).
set -eu
umask 077
MARKER=PYWEB_LAB1_DEPLOYMENT_OK

die() { printf '%s\n' "REMOTE RELEASE FAILED: $*" >&2; exit 1; }
identifier() {
    case "$1" in ''|*[!a-z0-9-]*|-*) die 'Invalid release/channel identifier';; esac
    [ "${#1}" -le 101 ] || die 'Identifier is too long'
}
guard() {
    g_path=$1
    case "$g_path" in /*) ;; *) die 'Path must be absolute';; esac
    while [ "$g_path" != / ]; do
        [ ! -L "$g_path" ] || die "Symbolic links are not allowed: $g_path"
        g_path=${g_path%/*}
        [ -n "$g_path" ] || g_path=/
    done
}
guard_tree() {
    guard "$1"
    [ -d "$1" ] || die "Directory is missing: $1"
    [ -z "$(find "$1" -type l -print)" ] || die 'Release contains a symbolic link'
}
target_for() {
    identifier "$1"
    if [ "$1" = main ]; then printf '%s\n' "$root";
    else printf '%s\n' "$root/previews/$1"; fi
}
release_of() {
    guard "$1/.release-id"
    if [ -f "$1/.release-id" ]; then
        m_release=$(cat "$1/.release-id")
        identifier "$m_release"
        printf '%s\n' "$m_release"
    elif [ -f "$1/index.html" ]; then printf '%s\n' legacy;
    fi
}
result_for() {
    m_target=$(target_for "$1")
    m_id=$(release_of "$m_target")
    [ -n "$m_id" ] || die 'No published version exists'
    if [ "$m_id" = legacy ]; then m_marker=$MARKER;
    else m_marker=PYWEB_LAB1_RELEASE:$m_id; fi
    m_previous=false
    [ ! -s "$state/history/$1.previous" ] || m_previous=true
    printf 'release=%s\nmarker=%s\nhas_previous=%s\n' "$m_id" "$m_marker" "$m_previous"
}
recover_transaction() {
    [ -d "$state/transaction" ] || return 0
    guard_tree "$state/transaction"
    r_channel=$(cat "$state/transaction/channel")
    r_operation=$(cat "$state/transaction/operation")
    identifier "$r_channel"; identifier "$r_operation"
    r_target=$(target_for "$r_channel")
    r_incoming=$state/staging/$r_operation
    r_outgoing=$state/backups/$r_channel/$r_operation
    guard "$r_target"; guard "$r_incoming"; guard "$r_outgoing"
    guard "$state/history/$r_channel.previous"
    guard "$state/history/$r_channel.previous.tmp"
    if [ -d "$r_outgoing" ]; then
        if [ -d "$r_target" ]; then
            [ ! -e "$r_incoming" ] || die 'Ambiguous interrupted transaction'
            mv "$r_target" "$r_incoming"
        fi
        mv "$r_outgoing" "$r_target"
    elif [ "$(cat "$state/transaction/had-target")" = false ] && [ -d "$r_target" ] && [ ! -e "$r_incoming" ]; then
        mv "$r_target" "$r_incoming"
    fi
    cp "$state/transaction/previous" "$state/history/$r_channel.previous.tmp"
    mv "$state/history/$r_channel.previous.tmp" "$state/history/$r_channel.previous"
    # Only files created by this script inside the validated private journal.
    rm "$state/transaction/channel" "$state/transaction/operation" "$state/transaction/had-target" "$state/transaction/previous"
    rmdir "$state/transaction"
}
finish() {
    f_status=$?
    trap - 0 1 2 15
    set +e
    if [ "$f_status" -ne 0 ] && [ "${owns_lock:-false}" = true ] && [ -d "$state/transaction" ]; then
        (set -e; recover_transaction)
        [ "$?" -eq 0 ] || f_status=1
    fi
    if [ "${owns_lock:-false}" = true ] && [ "$(cat "$state/lock" 2>/dev/null)" = "$$ $operation" ]; then
        rm "$state/lock"
    fi
    [ ! -f "$state/lock-$operation" ] || rm "$state/lock-$operation"
    if [ "${owns_reclaim:-false}" = true ]; then rmdir "$state/lock-recovery"; fi
    exit "$f_status"
}
acquire_lock() {
    # An atomic hard link exposes an already complete owner record (no empty-PID race).
    guard "$state/lock"; guard "$state/lock-$operation"; guard "$state/lock-recovery"
    [ ! -d "$state/lock" ] || die 'Lock path must not be a directory'
    [ ! -e "$state/lock-$operation" ] || die 'Lock candidate already exists'
    printf '%s %s\n' "$$" "$operation" > "$state/lock-$operation"
    if ! ln "$state/lock-$operation" "$state/lock" 2>/dev/null; then
        mkdir "$state/lock-recovery" 2>/dev/null || die 'Lock recovery is already in progress'
        owns_reclaim=true
        lock_pid=$(awk 'NR == 1 {print $1}' "$state/lock")
        case "$lock_pid" in ''|*[!0-9]*) die 'Invalid lock owner; manual inspection required';; esac
        if kill -0 "$lock_pid" 2>/dev/null; then die 'Another release operation is running'; fi
        rm "$state/lock"
        ln "$state/lock-$operation" "$state/lock" || die 'Lock was acquired by another operation'
        owns_lock=true
        rmdir "$state/lock-recovery"
        owns_reclaim=false
    else owns_lock=true; fi
    rm "$state/lock-$operation"
}
switch_release() {
    s_channel=$1; s_operation=$2; s_incoming=$3
    s_target=$(target_for "$s_channel")
    guard_tree "$s_incoming"; guard "$s_target"
    s_release=$(release_of "$s_incoming")
    [ -n "$s_release" ] || die 'Release metadata is missing'
    grep -F "$MARKER" "$s_incoming/index.html" >/dev/null || die 'Release healthcheck marker is missing'
    if [ "$s_release" != legacy ]; then
        grep -F "<!-- PYWEB_LAB1_RELEASE:$s_release -->" "$s_incoming/index.html" >/dev/null || die 'Release healthcheck marker is missing'
    fi
    [ ! -e "$s_incoming/previews" ] || die 'previews is reserved for branch deployments'
    if [ "$s_channel" = main ] && [ -d "$s_target/previews" ]; then
        guard_tree "$s_target/previews"
        cp -Rp "$s_target/previews" "$s_incoming/previews"
    fi
    mkdir -p "${s_target%/*}"
    chmod 755 "${s_target%/*}"
    if [ "$s_channel" != main ]; then chmod 755 "$root"; fi
    s_outgoing=$state/backups/$s_channel/$s_operation
    guard "$s_outgoing"
    [ ! -e "$s_outgoing" ] || die 'Backup already exists'
    mkdir -p "${s_outgoing%/*}"
    s_previous=$(release_of "$s_target")
    guard "$state/committed-$s_operation"
    [ ! -e "$state/committed-$s_operation" ] || die 'Release operation was already committed'
    s_journal=$state/txn-$s_operation
    guard "$s_journal"
    mkdir "$s_journal"
    printf '%s\n' "$s_channel" > "$s_journal/channel"
    printf '%s\n' "$s_operation" > "$s_journal/operation"
    if [ -d "$s_target" ]; then printf 'true\n' > "$s_journal/had-target";
    else printf 'false\n' > "$s_journal/had-target"; fi
    if [ -f "$state/history/$s_channel.previous" ]; then
        cp "$state/history/$s_channel.previous" "$s_journal/previous"
    else : > "$s_journal/previous"; fi
    [ ! -e "$state/transaction" ] || die 'Transaction was not recovered'
    mv "$s_journal" "$state/transaction"
    if [ -d "$s_target" ]; then mv "$s_target" "$s_outgoing"; fi
    # FAILPOINT old-moved
    mv "$s_incoming" "$s_target"
    # FAILPOINT new-moved
    if [ -n "$s_previous" ]; then
        printf '%s\n' "$s_operation" > "$state/history/$s_channel.previous.tmp"
    else : > "$state/history/$s_channel.previous.tmp"; fi
    mv "$state/history/$s_channel.previous.tmp" "$state/history/$s_channel.previous"
    # Rename is the commit point. A leftover committed journal is not undone.
    mv "$state/transaction" "$state/committed-$s_operation"
    result_for "$s_channel"
}
run_action() {
    action=$1; channel=$2; release=$3; operation=$4
    identifier "$channel"; identifier "$operation"
    [ -z "$release" ] || identifier "$release"
    case "$action" in prepare|activate|rollback|recover) ;; *) die 'Unknown action';; esac
    guard "$root"; guard "$state"
    mkdir -p "${root%/*}" "$state"
    chmod 755 "${root%/*}"; chmod 700 "$state"
    for d in staging backups history; do guard "$state/$d"; mkdir -p "$state/$d"; done
    # POSIX df; refuse cross-filesystem copy-and-delete behaviour of mv.
    public_device=$(df -P "${root%/*}" | awk 'NR == 2 {print $1}')
    state_device=$(df -P "$state" | awk 'NR == 2 {print $1}')
    [ -n "$public_device" ] && [ -n "$state_device" ] && [ "$public_device" = "$state_device" ] || die 'Public site and staging must be on the same filesystem'
    owns_lock=false; owns_reclaim=false
    trap finish 0
    trap 'exit 129' 1; trap 'exit 130' 2; trap 'exit 143' 15
    acquire_lock
    recover_transaction
    target=$(target_for "$channel")
    guard "$target"; guard "$state/history/$channel.previous"
    case "$action" in
        prepare)
            identifier "$release"
            stage=$state/staging/$release
            guard "$stage"
            [ ! -e "$state/committed-$release" ] || die 'Release operation was already committed'
            mkdir "$stage" || die 'Release staging directory already exists'
            chmod 755 "$stage"
            printf 'stage=%s\nroot=%s\n' "$stage" "$root"
            ;;
        activate)
            identifier "$release"
            stage=$state/staging/$release
            [ "$(release_of "$stage")" = "$release" ] || die 'Staging release does not match requested release'
            switch_release "$channel" "$release" "$stage"
            ;;
        rollback)
            if [ -n "$release" ] && [ "$(release_of "$target")" != "$release" ]; then
                die 'Current release changed; refusing automatic rollback'
            fi
            [ -s "$state/history/$channel.previous" ] || die 'No previous version is available'
            previous=$(cat "$state/history/$channel.previous")
            identifier "$previous"
            backup=$state/backups/$channel/$previous
            guard_tree "$backup"
            stage=$state/staging/$operation
            guard "$stage"; mkdir "$stage"; chmod 755 "$stage"
            for entry in "$backup"/* "$backup"/.[!.]* "$backup"/..?*; do
                [ -e "$entry" ] || continue
                if [ "$channel" = main ] && [ "$entry" = "$backup/previews" ]; then continue; fi
                cp -Rp "$entry" "$stage/"
            done
            switch_release "$channel" "$operation" "$stage"
            ;;
        recover) result_for "$channel";;
    esac
}
