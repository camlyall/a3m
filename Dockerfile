ARG SYSTEM_IMAGE=ubuntu:20.04

#
# Base
#

FROM ${SYSTEM_IMAGE} AS base

ENV DEBIAN_FRONTEND noninteractive
ENV PYTHONUNBUFFERED 1

RUN set -ex \
	&& apt-get update \
	&& apt-get install -y --no-install-recommends \
		apt-transport-https \
		curl \
		git \
		gpg-agent \
		locales \
		locales-all \
		software-properties-common \
		python3 \
		python3-pip \
		python3-venv \
	&& rm -rf /var/lib/apt/lists/* \
	&& update-alternatives --install /usr/bin/python python /usr/bin/python3.8 1

# Set the locale
RUN locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

# OS dependencies
RUN set -ex \
	&& curl -s https://packages.archivematica.org/GPG-KEY-archivematica | apt-key add - \
	&& add-apt-repository --no-update --yes "deb [arch=amd64] http://packages.archivematica.org/1.11.x/ubuntu-externals bionic main" \
	&& add-apt-repository --no-update --yes "deb http://archive.ubuntu.com/ubuntu/ focal multiverse" \
	&& add-apt-repository --no-update --yes "deb http://archive.ubuntu.com/ubuntu/ focal-security universe" \
	&& add-apt-repository --no-update --yes "deb http://archive.ubuntu.com/ubuntu/ focal-updates multiverse" \
	&& apt-get update \
	&& apt-get install -y --no-install-recommends \
		atool \
		clamav \
		ffmpeg \
		ghostscript \
		coreutils \
		libavcodec-extra \
		imagemagick \
		inkscape \
		jhove \
		libimage-exiftool-perl \
		libevent-dev \
		libjansson4 \
		mediainfo \
		nailgun \
		openjdk-8-jre-headless \
		p7zip-full \
		pbzip2 \
		pst-utils \
		rsync \
		siegfried \
		sleuthkit \
		tesseract-ocr \
		tree \
		unar \
		unrar-free \
		uuid \
	&& rm -rf /var/lib/apt/lists/*

# Excluded packages
# ufraw, bulk-extrator, mediaconch

# Download ClamAV virus signatures
RUN freshclam --quiet

# Create a3m user
RUN set -ex \
	&& groupadd --gid 333 --system a3m \
	&& useradd --uid 333 --gid 333 --create-home --home-dir /home/a3m --system a3m \
	&& mkdir -p /home/a3m/.local/share/a3m \
	&& chown -R a3m:a3m /home/a3m/.local


#
# Archivematica
#

FROM base AS a3m

ARG REQUIREMENTS=/a3m/requirements-dev.txt
ARG DJANGO_SETTINGS_MODULE=a3m.settings.common
ENV DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE}

COPY ./a3m/externals/fido/ /usr/lib/archivematica/archivematicaCommon/externals/fido/
COPY ./a3m/externals/fiwalk_plugins/ /usr/lib/archivematica/archivematicaCommon/externals/fiwalk_plugins/

COPY ./requirements.txt /a3m/requirements.txt
COPY ./requirements-dev.txt /a3m/requirements-dev.txt

RUN python -m venv /a3m-venv
ENV PATH="/a3m-venv/bin:$PATH"
RUN python -m pip install --upgrade pip \
	&& python -m pip install -r ${REQUIREMENTS}

COPY . /a3m
WORKDIR /a3m

USER a3m

ENTRYPOINT ["python", "-m", "a3m"]
