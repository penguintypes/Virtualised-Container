#!/usr/bin/env bash
set -euo pipefail

action="${1:-}"
name="${2:-}"

store="/tmp/vcontainer-images"
oci_store="/tmp/vcontainer-oci"
rootfs="$store/$name/rootfs"


#if [ "$#" -ne 3 ] || [ "$1" != "import" ]; then
 #   echo "usage: $0 import IMAGE_NAME ARCHIVE" >&2
 #   exit 2
#fi

#name="$2"
#archive="$3"

case "$name" in
    ""|*[!a-zA-Z0-9_.-]*)
        echo "invalid image name: $name" >&2
        exit 2
        ;;
esac

case "$action" in
    import)
        archive="${3:-}"
        [ -n "$archive" ] || {
            echo "usage: $0 import IMAGE ARCHIVE" >&2
            exit 2
        }

        [ ! -e "$store/$name" ] || {
            echo "image already exists: $name" >&2
            exit 1
        }

        mkdir -p "$rootfs"

        case "$archive" in
            *.tar|*.tar.gz|*.tgz|*.tar.xz)
                tar -xpf "$archive" -C "$rootfs"
                ;;
            *.cpio.gz)
                gzip -dc "$archive" |
                    (cd "$rootfs" && cpio -idmu --quiet)
                ;;
            *.cpio)
                (cd "$rootfs" && cpio -idmu --quiet < "$archive")
                ;;
            *)
                echo "supported: tar, tar.gz, tgz, tar.xz, cpio, cpio.gz" >&2
                exit 2
                ;;
        esac
        ;;

    pull)
        reference="${3:-docker.io/library/$name:latest}"
        [ ! -e "$store/$name" ] || {
            echo "image already exists: $name" >&2
            exit 1
        }

        mkdir -p "$oci_store"

        skopeo copy \
            "docker://$reference" \
            "oci:$oci_store/$name:latest"

        umoci unpack \
            --image "$oci_store/$name:latest" \
            "$store/$name"
        ;;

    *)
        echo "usage:" >&2
        echo " $0 import IMAGE ARCHVE" >&2
        echo " $0 pull IMAGE" >&2
        exit 2
        ;;
esac

if [ ! -x "$rootfs/bin/sh" ]; then
    echo "import failed: image has no executable /bin/sh: $name" >&2
    exit 1;
fi

echo "Imported image: $name"
echo "Rootfs path: $rootfs"
