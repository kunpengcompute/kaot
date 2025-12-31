#!/bin/bash
# Copyright(c) Huawei Technologies Co., Ltd. 2025. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ===========================================================================
# -*- coding: utf-8 -*-
set -uo pipefail

# ----------------------------
# 配置区
# ----------------------------
DOWNLOAD_DIR="./install_files"
DOWNLOAD_URLS=(
  "http://www.colm.net/files/ragel/ragel-6.10.tar.gz"
  "https://archives.boost.io/release/1.87.0/source/boost_1_87_0.tar.gz"
  "https://sourceforge.net/projects/pcre/files/pcre/8.43/pcre-8.43.tar.gz"
  "https://gitee.com/kunpengcompute/hyperscan/raw/khsel/build.sh"
  "https://gitee.com/kunpengcompute/hyperscan/archive/refs/tags/v5.4.2.aarch64.zip"
  "https://gitee.com/kunpengcompute/hyperscan/raw/khsel/khsel_enhanced.patch"
)
FILE_NAMES=(
  "ragel-6.10.tar.gz"
  "boost_1_87_0.tar.gz"
  "pcre-8.43.tar.gz"
  "build.sh"
  "v5.4.2.aarch64.zip"
  "khsel_enhanced.patch"

)
DEPENDENCIES=("gcc" "sqlite" "make" "cmake" "tar" "sqlite-devel" "gcc-c++" "patch")
RAGEL_TAR_FILENAME="ragel-6.10.tar.gz"
BOOST_TAR_FILENAME="boost_1_87_0.tar.gz"

SKIP_RAGEL=0
SKIP_BOOST=0

log() { echo "$*"; }
err() { log "ERROR: $*" >&2; }

usage() {
  cat <<EOF
Usage: $0 [-d <dir>]
  -d <dir>   指定已下载文件所在目录（脚本仅检查，不下载；若缺失则报错并退出）
  不指定 -d 时脚本会在 ${DOWNLOAD_DIR} 下载缺失文件
EOF
  exit 1
}

# 参数解析
CHECK_ONLY_DIR=""
while [ $# -gt 0 ]; do
  case "$1" in
    -d)
      if [ -z "${2:-}" ]; then
        err "缺少 -d 的目录参数"
        usage
      fi
      CHECK_ONLY_DIR="$2"
      shift 2
      ;;
    -skip_ragel)
      SKIP_RAGEL=1
      shift
      ;;
    -skip_boost)
      SKIP_BOOST=1
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      err "未知参数: $1"
      usage
      ;;
  esac
done

# ----------------------------
# 公共工具函数
# ----------------------------
file_exists_and_not_empty() {
  [ -f "$1" ] && [ -s "$1" ]
}

dir_exists() {
  [ -d "$1" ]
}

extract_tar_gz() {
  local tarfile="$1"
  log "解压 $tarfile"
  tar -xzf "$tarfile"
}

extract_zip() {
  local zipfile="$1"
  log "解压 $zipfile"
  unzip -o "$zipfile" >/dev/null 2>&1
}

# 通用解压并查找源码目录函数
extract_and_check_dir() {
  local tarfile="$1"
  local dir_pattern="$2"
  if [ -z "$tarfile" ] || [ -z "$dir_pattern" ]; then
    err "未指定 tar 文件名或目录模式"
    return 1
  fi
  if [ ! -f "$tarfile" ] || [ ! -s "$tarfile" ]; then
    err "包不存在或为空: $tarfile"
    return 1
  fi
  log "解压：$tarfile"
  if ! tar -zxf "$tarfile"; then
    err "解压失败: $tarfile"
    return 1
  fi
  local topdir
  topdir=$(ls -d $dir_pattern 2>/dev/null | head -n1 || true)
  if [ -z "$topdir" ] || [ ! -d "$topdir" ]; then
    err "无法定位解压后的源码目录: $dir_pattern，请手动检查"
    return 1
  fi
  log "已解压到目录: $topdir"
  return 0
}

find_first_dir() {
  # 查找当前目录下第一个匹配的目录
  local pattern="$1"
  ls -d $pattern 2>/dev/null | head -n1 || true
}

find_first_file() {
  # 查找当前目录下第一个匹配的文件
  local pattern="$1"
  ls -1 $pattern 2>/dev/null | head -n1 || true
}

run_with_log() {
  log "执行命令: $*"
  "$@"
}

ensure_in_download_dir() {
  if [ "$(pwd -P)" != "$download_dir_abs" ]; then
    log "检测到当前目录不在下载目录，返回到: $download_dir_abs"
    cd "$download_dir_abs" || { err "无法返回到下载目录: $download_dir_abs"; exit 1; }
  fi
}

# ----------------------------
# 依赖检查与安装
# ----------------------------
check_installed_deps() {
  local missing=()
  for pkg in "${DEPENDENCIES[@]:-}"; do
    if ! rpm -q "$pkg" >/dev/null 2>&1; then
      missing+=("$pkg")
    fi
  done
  if [ ${#missing[@]} -gt 0 ]; then
    for m in "${missing[@]}"; do log "$m"; done
  fi
}

yum_repo_ok() {
  command -v yum >/dev/null 2>&1 && yum repolist enabled >/dev/null 2>&1
}

yum_query_available() {
  local pkgs=("$@")
  local found=()
  for p in "${pkgs[@]}"; do
    if command -v yumdownloader >/dev/null 2>&1 && yumdownloader --urls "$p" >/dev/null 2>&1; then
      found+=("$p")
    elif yum list available "$p" >/dev/null 2>&1 || yum info "$p" >/dev/null 2>&1; then
      found+=("$p")
    fi
  done
  if [ ${#found[@]} -gt 0 ]; then
    for f in "${found[@]}"; do log "$f"; done
  fi
}

install_via_yum() {
  local pkgs=("$@")
  [ ${#pkgs[@]} -eq 0 ] && return 0
  command -v yum >/dev/null 2>&1 || { err "系统缺少 yum，无法安装依赖"; return 1; }
  log "尝试通过 yum 安装：${pkgs[*]}"
  yum -y install "${pkgs[@]}"
}

# 通用源码包编译安装函数
build_and_install_from_tar() {
  # $1: tar包名
  # $2: 解压后目录名模式（如 ragel* 或 boost_*）
  # $3: configure命令（如 ./configure 或 ./bootstrap.sh ...）
  # $4: make命令（如 make 或 ./b2 toolset=gcc ...）
  # $5: install命令（如 make install 或 ./b2 install ...）
  # $6: 是否忽略 make/install 错误（0=致命，1=仅警告）
  local tarfile="$1"
  local dir_pattern="$2"
  local configure_cmd="$3"
  local make_cmd="$4"
  local install_cmd="$5"
  local ignore_error="${6:-0}"

  # 解压并查找源码目录
  extract_and_check_dir "$tarfile" "$dir_pattern" || return 1
  local topdir
  topdir=$(ls -d $dir_pattern 2>/dev/null | head -n1 || true)
  log "进入源码目录: $topdir"
  pushd "$topdir" >/dev/null || { err "进入 $topdir 失败"; return 1; }

  log "执行 configure: $configure_cmd"
  if ! eval "$configure_cmd"; then
    err "configure 失败: $configure_cmd"
    popd >/dev/null
    return 1
  fi

  log "执行 build: $make_cmd"
  if ! eval "$make_cmd"; then
    if [ "$ignore_error" = "1" ]; then
      log "警告: build 命令失败但被忽略: $make_cmd"
    else
      err "build 失败: $make_cmd"
      popd >/dev/null
      return 1
    fi
  fi

  log "执行 install: $install_cmd"
  if ! eval "$install_cmd"; then
    if [ "$ignore_error" = "1" ]; then
      log "警告: install 命令失败但被忽略: $install_cmd"
    else
      err "install 失败: $install_cmd"
      popd >/dev/null
      return 1
    fi
  fi

  popd >/dev/null
  log "源码包 $topdir 构建和安装完成"
  return 0
}

# Boost专用动态库刷新
refresh_ldconfig() {
  log "Running ldconfig to refresh dynamic linker cache"
  if ! ldconfig; then
    err "ldconfig failed"
    return 1
  fi
  return 0
}

# ragel编译安装
install_ragel() {
  build_and_install_from_tar \
    "$RAGEL_TAR_FILENAME" \
    "ragel*" \
    "./configure" \
    "make -j$(nproc 2>/dev/null || echo 1)" \
    "make install" \
    0
  # 检查ragel命令
  if command -v ragel >/dev/null 2>&1; then
    log "ragel installed and available: $(ragel -v 2>&1 | head -n1)"
    return 0
  else
    err "ragel executable not found after install"
    return 1
  fi
}

# boost编译安装
install_boost() {
  build_and_install_from_tar \
    "$BOOST_TAR_FILENAME" \
    "boost_*" \
    "./bootstrap.sh --with-libraries=all --with-toolset=gcc" \
    "./b2 toolset=gcc -j$(nproc 2>/dev/null || echo 1)" \
    "./b2 install --prefix=/usr" \
    1
  refresh_ldconfig || return 1
  log "Boost install finished (errors in build/install are ignored)"
  return 0
}

install_rpm_from_zip() {
  local zipfile="$1"
  extract_zip "$zipfile" || return 1
  local rpm_file
  rpm_file=$(find_first_file "boostkit-ksl*.rpm")
  if [ -z "$rpm_file" ]; then
    err "未找到 boostkit-ksl*.rpm，KSL 安装失败"
    return 1
  fi
  log "安装 KSL RPM：$rpm_file"
  local out
  out=$(rpm -ivh "$rpm_file" 2>&1)
  local rc=$?
  if [ $rc -eq 0 ] || echo "$out" | grep -qi "already installed"; then
    log "KSL RPM 安装完成或已安装: $rpm_file"
    return 0
  fi
  err "安装 KSL RPM 失败: $rpm_file"
  log "$out" | sed 's/^/  /' >&2
  return $rc
}

run_build_sh_from_zip() {
  local zipfile="$1"
  extract_zip "$zipfile" || return 1
  if file_exists_and_not_empty "./build.sh"; then
    log "在下载目录找到 build.sh，执行 ./build.sh"
    sh ./build.sh || { err "执行 Hyperscan build.sh 失败"; return 1; }
    log "Hyperscan build.sh 执行完成"
    return 0
  fi
  local topdir
  topdir=$(find_first_dir "hyperscan*")
  if [ -n "$topdir" ] && file_exists_and_not_empty "$topdir/build.sh"; then
    log "在 $topdir 找到 build.sh，进入并执行"
    (cd "$topdir" && sh build.sh) || { err "执行 Hyperscan build.sh 失败：$topdir/build.sh"; return 1; }
    log "Hyperscan build.sh 执行完成（$topdir）"
    return 0
  fi
  err "未找到 build.sh，执行失败"
  return 1
}

build_hyperscan_from_source() {
  # 3) 编译 Hyperscan：准备 boost 头文件、拷贝 pcre、修改 pcre/CMakeLists.txt 并 cmake/make
  local hyperscan_dir="${1:-hyperscan}"   # 相对于 DOWNLOAD_DIR

  # 定位 Hyperscan 源码目录
  local hs_src=""
  if [ -d "$hyperscan_dir" ]; then
    hs_src="$hyperscan_dir"
  else
    hs_src=$(ls -d hyperscan* 2>/dev/null | head -n1 || true)
  fi
  if [ -z "$hs_src" ] || [ ! -d "$hs_src" ]; then
    err "未找到 Hyperscan 源码目录: $hyperscan_dir"
    return 1
  fi

  # 定位 Boost 解压目录
  local boost_src
  boost_src=$(ls -d boost_* 2>/dev/null | head -n1 || true)
  if [ -z "$boost_src" ] || [ ! -d "$boost_src" ]; then
    err "未找到 Boost 源码目录（请先解压 Boost）: boost_*"
    return 1
  fi
  boost_src=$(realpath "$boost_src")

  log "Hyperscan 源码目录: $hs_src"
  log "Boost 源码目录: $boost_src"

  # 在 hyperscan 源码下创建 include 目录并建立到 boost 的符号链接（使用绝对路径）
  pushd "$hs_src" >/dev/null || { err "进入 $hs_src 失败"; return 1; }

  mkdir -p include
  # 如果已有链接或目录，先移除再创建
  if [ -L include/boost ] || [ -d include/boost ]; then
    rm -rf include/boost
  fi
  log "创建 Boost 头文件软链接: include/boost -> $boost_src/boost"
  ln -s "$boost_src/boost" include/boost || { err "创建软链接失败"; popd >/dev/null; return 1; }
  popd >/dev/null

  # 拷贝 PCRE 源码到 hyperscan/pcre
  local pcre_src="pcre-8.43"
  if [ ! -d "$pcre_src" ]; then
    pcre_src=$(ls -d pcre-* 2>/dev/null | grep "pcre-8.43" | head -n1 || true)
  fi
  if [ -z "$pcre_src" ] || [ ! -d "$pcre_src" ]; then
    err "未找到 PCRE 源码目录，请先解压 pcre-8.43.tar.gz"
    return 1
  fi

  rm -rf "$hs_src/pcre"
  log "拷贝 PCRE 到 Hyperscan 源码: $pcre_src -> $hs_src/pcre"
  cp -rf "$pcre_src" "$hs_src/pcre" || { err "拷贝 pcre 失败"; return 1; }

  # 注释掉 pcre/CMakeLists.txt 的第 77 行（兼容老 CMake）
  local pcre_cmake="$hs_src/pcre/CMakeLists.txt"
  if [ -f "$pcre_cmake" ]; then
    log "注释 pcre/CMakeLists.txt 第 77 行，兼容老版本 CMake"
    sed -i '77s/^[[:space:]]*/#&/' "$pcre_cmake" || true
  else
    log "警告: 未找到 $pcre_cmake，跳过注释步骤"
  fi

  # 进入 Hyperscan 源码目录进行编译
  pushd "$hs_src" >/dev/null || { err "进入 $hs_src 失败"; return 1; }

  # 三种编译模式：静态、共享、debug
  local builds=(
    "static:"
    "shared:-DBUILD_SHARED_LIBS=ON"
    "debug:-DCMAKE_BUILD_TYPE=DEBUG"
  )

  local build
  for build in "${builds[@]}"; do
    local mode="${build%%:*}"
    local extra_opts="${build#*:}"

    local build_dir="build_${mode}"
    rm -rf "$build_dir"
    mkdir -p "$build_dir" || { err "创建构建目录失败: $build_dir"; popd >/dev/null; return 1; }
    pushd "$build_dir" >/dev/null || { err "进入构建目录失败: $build_dir"; popd >/dev/null; return 1; }

    log "编译 Hyperscan (${mode})，构建目录: $hs_src/$build_dir"
    if [ -z "$extra_opts" ]; then
      log "执行 cmake .."
      if ! cmake ..; then
        err "cmake 配置失败（模式: $mode）"
        popd >/dev/null
        popd >/dev/null
        return 1
      fi
    else
      IFS=' ' read -r -a cmake_extra_arr <<< "$extra_opts"
      log "执行 cmake .. ${cmake_extra_arr[*]:-}"
      if ! cmake .. "${cmake_extra_arr[@]}"; then
        err "cmake 配置失败（模式: $mode）"
        popd >/dev/null
        popd >/dev/null
        return 1
      fi
    fi

    local jobs=${MAKE_JOBS:-32}
    log "执行 make -j$jobs (模式: $mode)"
    if ! make -j"$jobs"; then
      err "make 构建失败（模式: $mode）"
      popd >/dev/null
      popd >/dev/null
      return 1
    fi

    local lib_path="$hs_src/$build_dir/lib"
    local lib64_path="$hs_src/$build_dir/lib64"
    local bin_path="$hs_src/$build_dir/bin"
    if [ -d "$lib_path" ]; then
      log "构建完成（模式: $mode）。产物目录: $lib_path"
    elif [ -d "$lib64_path" ]; then
      log "构建完成（模式: $mode）。产物目录: $lib64_path"
    else
      log "构建完成（模式: $mode）。构建目录: $hs_src/$build_dir（未找到 lib 或 lib64，请检查输出）"
    fi
    if [ -d "$bin_path" ]; then
      log "可执行文件目录: $bin_path"
    fi

    popd >/dev/null
  done

  log "全部编译模式完成。构建目录: $hs_src/build_static, $hs_src/build_shared, $hs_src/build_debug"
  popd >/dev/null
  return 0
}

# ----------------------------
# 主流程
# ----------------------------
main() {
  ORIG_PWD="$(pwd -P 2>/dev/null || pwd)"

  # 1. 文件检查/下载
  if [ -n "$CHECK_ONLY_DIR" ]; then
    DOWNLOAD_DIR="$CHECK_ONLY_DIR"
    log "模式：check-only，检查目录：$DOWNLOAD_DIR"
  else
    log "模式：download-if-missing，下载目录：$DOWNLOAD_DIR"
    mkdir -p "$DOWNLOAD_DIR" || { err "无法创建下载目录：$DOWNLOAD_DIR"; exit 1; }
    for i in "${!FILE_NAMES[@]}"; do
      fname="${FILE_NAMES[i]}"
      url="${DOWNLOAD_URLS[i]:-}"
      fpath="$DOWNLOAD_DIR/$fname"
      if ! file_exists_and_not_empty "$fpath"; then
        [ -z "$url" ] && { log "无下载链接（跳过）: $fname"; continue; }
        log "下载：$url -> $fpath"
        if command -v wget >/dev/null 2>&1; then
          wget --show-progress -O "$fpath" "$url"
        elif command -v curl >/dev/null 2>&1; then
          curl -fSL --retry 3 -o "$fpath" "$url" --progress-bar
        else
          log "系统缺少 curl/wget，无法下载: $url"
        fi
      fi
    done
  fi

  cd "$DOWNLOAD_DIR" || { err "无法进入下载目录：$DOWNLOAD_DIR"; exit 1; }
  download_dir_abs="$(pwd -P)"
  log "步骤1 完成：文件检查/下载。当前目录: $(pwd -P)"
  ensure_in_download_dir

  # 2. 依赖检查与安装（sh 兼容写法）
  deps_missing_arr=""
  while IFS= read -r line; do
    [ -n "$line" ] && deps_missing_arr="$deps_missing_arr $line"
  done <<EOF
$(check_installed_deps | sed '/^$/d')
EOF
  set -- $deps_missing_arr
  if [ $# -ne 0 ]; then
    if ! yum_repo_ok; then
      err "yum 源不可用或系统缺少 yum，无法自动安装依赖，流程结束。请手动安装： $deps_missing_arr"
      cd "$ORIG_PWD" || true
      exit 1
    fi
    available_arr=""
    while IFS= read -r line; do
      [ -n "$line" ] && available_arr="$available_arr $line"
    done <<EOF
$(yum_query_available $deps_missing_arr | sed '/^$/d')
EOF
    unavailable=""
    for pkg in $deps_missing_arr; do
      local_found=0
      for a in $available_arr; do
        [ "$pkg" = "$a" ] && local_found=1 && break
      done
      [ "$local_found" -eq 0 ] && unavailable="$unavailable $pkg"
    done
    if [ -n "$unavailable" ]; then
      err "以下依赖在 yum 仓库中不可用，无法自动安装，流程结束： $unavailable"
      cd "$ORIG_PWD" || true
      exit 1
    fi
    install_via_yum $available_arr || { err "依赖安装失败，流程结束"; cd "$ORIG_PWD" || true; exit 1; }
  fi
  log "步骤2 完成：依赖检查/安装。当前目录: $(pwd -P)"
  ensure_in_download_dir

  # 3. ragel
  if [ "${SKIP_RAGEL:-0}" -eq 0 ] && file_exists_and_not_empty "$RAGEL_TAR_FILENAME"; then
    install_ragel || { err "ragel build/install failed"; exit 1; }
  fi
  log "步骤3 完成：ragel 编译/安装（或跳过）。当前目录: $(pwd -P)"
  ensure_in_download_dir

  # 4. boost
  if [ "${SKIP_BOOST:-0}" -eq 0 ] && file_exists_and_not_empty "$BOOST_TAR_FILENAME"; then
    install_boost || { err "Boost build/install failed"; exit 1; }
  fi
  log "步骤4 完成：Boost 编译/安装（或跳过）。当前目录: $(pwd -P)"
  ensure_in_download_dir

  # 5. sqlite 校验
  if ! command -v pkg-config >/dev/null 2>&1 || ! pkg-config --libs sqlite3 | grep -q -- -lsqlite3; then
    err "sqlite3 校验失败"
    exit 1
  fi
  log "步骤5 完成：sqlite 校验。当前目录: $(pwd -P)"
  ensure_in_download_dir

  # 6. pcre
  PCRE_TAR="pcre-8.43.tar.gz"
  if file_exists_and_not_empty "$PCRE_TAR"; then
    extract_and_check_dir "$PCRE_TAR" "pcre-*"
  else
    err "未找到 PCRE 包：$PCRE_TAR，安装失败，流程结束"
    exit 1
  fi
  log "步骤6 完成。当前目录: $(pwd -P)"
  ensure_in_download_dir

  # 7. KSL
  if file_exists_and_not_empty "BoostKit-ksl_2.5.2.zip"; then
    install_rpm_from_zip "BoostKit-ksl_2.5.2.zip" || { err "KSL 安装失败"; exit 1; }
  fi
  log "步骤7 完成。当前目录: $(pwd -P)"
  ensure_in_download_dir

  # 8. hyperscan build.sh
  if file_exists_and_not_empty "v5.4.2.aarch64.zip"; then
    run_build_sh_from_zip "v5.4.2.aarch64.zip" || { err "Hyperscan build.sh 执行失败"; exit 1; }
  fi
  log "步骤8 完成。当前目录: $(pwd -P)"
  ensure_in_download_dir

  # 9. hyperscan源码编译（可补充公共编译逻辑）
  if [ -d "hyperscan" ] || ls -d hyperscan* 1>/dev/null 2>&1; then
    build_hyperscan_from_source "hyperscan" || { err "Hyperscan source build failed"; exit 1; }
  fi
  log "步骤9 完成。当前目录: $(pwd -P)"
  ensure_in_download_dir
  cd "$ORIG_PWD" || true
  log "主流程完成"
}

main "$@"