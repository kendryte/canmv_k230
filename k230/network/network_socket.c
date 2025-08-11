/* Copyright (c) 2025, Canaan Bright Sight Co., Ltd
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 * 1. Redistributions of source code must retain the above copyright
 * notice, this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright
 * notice, this list of conditions and the following disclaimer in the
 * documentation and/or other materials provided with the distribution.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND
 * CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
 * INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
 * MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
 * DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
 * CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
 * SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
 * BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
 * SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 * INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
 * WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
 * NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */
#include <stdint.h>

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netdb.h>
#include <sys/select.h>
#include <sys/time.h>

#include <netinet/in.h> // For sockaddr_in
#include <poll.h>
#include <sys/ioctl.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/types.h> // For socket types
#include <unistd.h> // For close()

#include "py/mperrno.h"
#include "py/mphal.h"
#include "py/obj.h"
#include "py/runtime.h"
#include "py/stream.h"

#include "network/modnetwork.h"

// For auto-binding UDP sockets
#define BIND_PORT_RANGE_MIN (65000)
#define BIND_PORT_RANGE_MAX (65535)

#define debug_printf(...) // mp_printf(&mp_plat_print, __VA_ARGS__)

static __attribute__((unused)) uint16_t bind_port = BIND_PORT_RANGE_MIN;

/* NIC Protocol **************************************************************/
static void network_rt_wlan_socket_close(struct _mod_network_socket_obj_t* socket);
static int  network_rt_wlan_socket_settimeout(struct _mod_network_socket_obj_t* _socket, mp_uint_t timeout_ms, int* _errno);

// static int network_rt_wlan_socket_get_error(mod_network_socket_obj_t *_socket) {
//     int optval;
//     socklen_t optlen = sizeof(optval);

//     if (getsockopt(_socket->fileno, SOL_SOCKET, SO_ERROR, &optval, &optlen) < 0) {
//         debug_printf("socket_getsockopt() -> errno %d\n", errno);
//         return -1;
//     }

//     return optval;
// }

static int network_rt_wlan_socket_poll(mod_network_socket_obj_t* _socket, uint32_t rwf, int* _errno)
{
#if 0 // not support now
    int ret = 0;
    uint8_t flags = 0;
    struct pollfd fd[1];

    debug_printf("socket_polling_rw(%d, %d, %d)\n", _socket->fileno, _socket->timeout, rwf);
    if (_socket->timeout == 0) {
        // Non-blocking socket, next socket function will return EAGAIN
        return 0;
    }
    mp_uint_t start = mp_hal_ticks_ms();
    for (; !(flags & rwf); mp_hal_delay_ms(5)) {
        fd[0].fd = _socket->fileno;
        fd[0].events = POLLIN;
        fd[0].revents = 0;

        ret = poll(fd, 1, 1);
        flags = fd[0].revents;

        if (ret < 0 || flags & POLLERR) {
            *_errno = errno;
            debug_printf("socket_poll(%d) -> errno %d flags %d\n", _socket->fileno, *_errno, flags);
            return -1;
        }

        if (!(flags & rwf) && _socket->timeout != -1 &&
            mp_hal_ticks_ms() - start > _socket->timeout) {
            *_errno = MP_ETIMEDOUT;
            return -1;
        }
    }
#endif
    return 0;
}

static int network_rt_wlan_socke_setblocking(mod_network_socket_obj_t* _socket, bool blocking, int* _errno)
{
    int nonblocking = !blocking;
    // set socket in non-blocking mode
    if (ioctl(_socket->fileno, FIONBIO, &nonblocking) < 0) {
        *_errno = errno;
        network_rt_wlan_socket_close(_socket->fileno);
        return -1;
    }

    return 0;
}

static int network_rt_wlan_socket_listening(mod_network_socket_obj_t* _socket, int* _errno)
{
    int       optval;
    socklen_t optlen = sizeof(optval);

    if (getsockopt(_socket->fileno, SOL_SOCKET, SO_ACCEPTCONN, &optval, &optlen) < 0) {
        *_errno = errno;
        debug_printf("socket_getsockopt() -> errno %d\n", errno);
        return -1;
    }

    return optval;
}

static mp_uint_t network_rt_wlan_socket_auto_bind(mod_network_socket_obj_t* _socket, int* _errno)
{
#if 0 // not support now
    debug_printf("socket_autobind(%d)\n", _socket->fileno);
    if (_socket->bound == false && _socket->type != MOD_NETWORK_SOCK_RAW) {
        if (network_rt_wlan_socket_bind(socket, NULL, bind_port, _errno) != 0) {
            *_errno = errno;
            debug_printf("socket_bind() -> errno %d\n", *_errno);
            return -1;
        }
        bind_port++;
        bind_port = MIN(MAX(bind_port, BIND_PORT_RANGE_MIN), BIND_PORT_RANGE_MAX);
    }
#endif

    return 0;
}

// API for non-socket operations

static int network_rt_wlan_socket_gethostbyname(mp_obj_t nic, const char* name, mp_uint_t len, uint8_t* ip_out)
{
    if (len >= 256) {
        mp_printf(&mp_plat_print, "Host name length exceeds maximum of 255 bytes.\n");
        return -3;
    }

    // Make a null-terminated copy of hostname
    char hostname[256] = { 0 };
    memcpy(hostname, name, len);
    hostname[len] = '\0';

    struct hostent* he = gethostbyname(hostname);
    if (he == NULL || he->h_addrtype != AF_INET || he->h_length != 4) {
        mp_printf(&mp_plat_print, "Failed to resolve hostname: %s\n", hostname);
        return -1;
    }

    memcpy(ip_out, he->h_addr, 4);
    return 0;
}

// API for socket operations; return -1 on error
static int network_rt_wlan_socket_socket(struct _mod_network_socket_obj_t* _socket, int* _errno)
{
    debug_printf("socket_socket(%d %d %d)\n", _socket->domain, _socket->type, _socket->proto);

    int fd, domain, type;

    switch (_socket->type) {
    case MOD_NETWORK_SOCK_STREAM:
        type = SOCK_STREAM;
        break;

    case MOD_NETWORK_SOCK_DGRAM:
        type = SOCK_DGRAM;
        break;

    case MOD_NETWORK_SOCK_RAW:
        type = SOCK_RAW;
        break;

    default:
        *_errno = MP_EINVAL;
        return -1;
    }

    if (MOD_NETWORK_AF_INET == _socket->domain) {
        domain = AF_INET;
    } else if (MOD_NETWORK_AF_INET6 == _socket->domain) {
        domain = AF_INET6;
    } else {
        *_errno = MP_EAFNOSUPPORT;
        return -1;
    }

    fd = socket(domain, type, _socket->proto);
    if (fd < 0) {
        *_errno = errno;
        mp_printf(&mp_plat_print, "socket_socket() -> errno %d\n", errno);
        return -1;
    }

    // set socket state
    _socket->fileno   = fd;
    _socket->bound    = false;
    _socket->callback = MP_OBJ_NULL;

    return network_rt_wlan_socket_settimeout(_socket, 500, _errno);
}

static void network_rt_wlan_socket_close(struct _mod_network_socket_obj_t* socket)
{
    if (socket->callback != MP_OBJ_NULL) {
        // mp_sched_lock();
        // socket->callback = MP_OBJ_NULL;
        // mp_obj_list_remove(MP_STATE_PORT(mp_wifi_sockpoll_list), socket);
        // mp_sched_unlock();
    }

    if (socket->fileno >= 0) {
        close(socket->fileno);
        socket->fileno = -1; // Mark socket FD as invalid
    }
}

static int network_rt_wlan_socket_bind(struct _mod_network_socket_obj_t* _socket, byte* ip, mp_uint_t port, int* _errno)
{
    debug_printf("socket_bind(%d, %d)\n", _socket->fileno, port);

    struct sockaddr_in addr;
    addr.sin_family = _socket->domain;
    addr.sin_port   = htons(port);
    memcpy(&addr.sin_addr, ip, MOD_NETWORK_IPADDR_BUF_SIZE);

    int ret = bind(_socket->fileno, (struct sockaddr*)&addr, sizeof(addr));
    if (ret < 0) {
        *_errno = errno;
        // network_rt_wlan_socket_close(_socket);
        debug_printf("socket_bind(%d, %d) -> errno: %d\n", _socket->fileno, port, *_errno);
        return -1;
    }

    // Mark socket as bound to avoid auto-binding.
    _socket->bound = true;

    return 0;
}

static int network_rt_wlan_socket_listen(struct _mod_network_socket_obj_t* _socket, mp_int_t backlog, int* _errno)
{
    debug_printf("socket_listen(%d, %d)\n", _socket->fileno, backlog);

    int ret = listen(_socket->fileno, backlog);
    if (ret < 0) {
        *_errno = errno;
        // network_rt_wlan_socket_close(_socket);
        debug_printf("socket_listen() -> errno %d\n", *_errno);
        return -1;
    }
    return 0;
}

static int network_rt_wlan_socket_accept(struct _mod_network_socket_obj_t* _socket, struct _mod_network_socket_obj_t* socket2,
                                         byte* ip, mp_uint_t* port, int* _errno)
{
    mp_uint_t curr_tick_ms, stop_ms = 0;
    int32_t   timeout_ms = _socket->timeout;

    if (0 < timeout_ms) {
        stop_ms = mp_hal_ticks_ms() + timeout_ms;
    }

    debug_printf("socket_accept(%d)\n", _socket->fileno);

    if (network_rt_wlan_socket_poll(_socket, POLLIN, _errno) != 0) {
        return -1;
    }

    struct sockaddr_in addr;
    int                addrlen = sizeof(addr);
    addr.sin_family            = _socket->domain;

    *port  = 0;
    int fd = -1;

    do {
        *_errno = 0;
        MICROPY_EVENT_POLL_HOOK

        fd = accept(_socket->fileno, (struct sockaddr*)&addr, (socklen_t*)&addrlen);
        if (0 > fd) {
            *_errno = errno;

            debug_printf("socket_accept() -> errno %d %d\n", *_errno, fd);

            if (EAGAIN == *_errno) {
                goto _check_timeout;
            }

            return -1;
        }

    _check_timeout:
        if (0x00 == timeout_ms) { // non blocking
            *_errno = EAGAIN;
            return -1;
        } else if ((-1) == timeout_ms) { // blocking
        } else {
            curr_tick_ms = mp_hal_ticks_ms();
            if (curr_tick_ms > stop_ms) {
                *_errno = EAGAIN;
                return -1;
            }
        }
    } while (0 > fd);

    *port = ntohs(addr.sin_port);
    memcpy(ip, &addr.sin_addr.s_addr, sizeof(addr.sin_addr));

    // set socket state
    socket2->fileno   = fd;
    socket2->bound    = false;
    socket2->callback = MP_OBJ_NULL;

    return network_rt_wlan_socket_settimeout(_socket, 500, _errno);
}

static int network_rt_wlan_socket_connect(struct _mod_network_socket_obj_t* _socket, byte* ip, mp_uint_t port, int* _errno)
{
    debug_printf("socket_connect(%d)\n", _socket->fileno);

    struct sockaddr_in addr;
    addr.sin_family = _socket->domain;
    addr.sin_port   = htons(port);
    memcpy(&addr.sin_addr, ip, MOD_NETWORK_IPADDR_BUF_SIZE);

    int ret = connect(_socket->fileno, (struct sockaddr*)&addr, sizeof(addr));
    if (ret < 0) {
        *_errno = errno;
        debug_printf("socket_connect() -> errno %d\n", *_errno);

        // network_rt_wlan_socket_close(_socket);

        // Poll for write.
        // if (_socket->timeout == 0 ||
        //     network_rt_wlan_socket_poll(_socket, POLLOUT, _errno) != 0) {
        //     return -1;
        // }

        return -1;
    }

    return 0;
}

static mp_uint_t network_rt_wlan_socket_send(struct _mod_network_socket_obj_t* _socket, const byte* buf, mp_uint_t len,
                                             int* _errno)
{
    debug_printf("socket_send(%d, %d)\n", _socket->fileno, len);

    if (network_rt_wlan_socket_poll(_socket, POLLOUT, _errno) != 0) {
        return -1;
    }

    int ret = send(_socket->fileno, buf, len, 0);
    if (ret < 0) {
        *_errno = errno;
        // network_rt_wlan_socket_close(_socket);
        debug_printf("socket_send() -> errno %d\n", *_errno);
        return -1;
    }
    return ret;
}

static mp_uint_t network_rt_wlan_socket_recv(struct _mod_network_socket_obj_t* _socket, byte* buf, mp_uint_t len, int* _errno)
{
    debug_printf("socket_recv(%d), len %d\n", _socket->fileno, len);

    // check if socket in listening state.
    if (network_rt_wlan_socket_listening(_socket, _errno) == 1) {
        *_errno = MP_ENOTCONN;
        return -1;
    }

    if (network_rt_wlan_socket_poll(_socket, POLLIN, _errno) != 0) {
        return -1;
    }

#if 0
    int ret = recv(_socket->fileno, buf, len, 0);
    if (ret < 0) {
        *_errno = errno;
        debug_printf("socket_recv() -> errno %d %d\n", *_errno, ret);
        // network_rt_wlan_socket_close(_socket);

        if(EAGAIN == *_errno) {
            return 0;
        }

        return -1;
    }

    return ret;
#else
    int       ret      = -1;
    mp_uint_t received = 0;

    mp_uint_t curr_tick_ms, stop_ms = 0;
    int32_t   timeout_ms = _socket->timeout;

    if (0 < timeout_ms) {
        stop_ms = mp_hal_ticks_ms() + timeout_ms;
    }

    do {
        *_errno = 0;
        MICROPY_EVENT_POLL_HOOK

        ret = recv(_socket->fileno, buf + received, len - received, 0);

        if (0 > ret) {
            *_errno = errno;

            debug_printf("socket_recv() -> errno %d %d\n", *_errno, ret);

            if (EAGAIN == *_errno) {
                goto _check_timeout;
            }
            break;
        } else {
            received += ret;
        }

    _check_timeout:
        if (0x00 == timeout_ms) { // non blocking
            return received;
        } else if ((-1) == timeout_ms) { // blocking
        } else {
            curr_tick_ms = mp_hal_ticks_ms();
            if (curr_tick_ms > stop_ms) {
                return received;
            }
        }
    } while (received < len);

    return received;
#endif
}

static mp_uint_t network_rt_wlan_socket_sendto(struct _mod_network_socket_obj_t* _socket, const byte* buf, mp_uint_t len,
                                               byte* ip, mp_uint_t port, int* _errno)
{
    debug_printf("socket_sendto(%d)\n", _socket->fileno);
    // Auto-bind the socket first if the socket is unbound.
    if (network_rt_wlan_socket_auto_bind(_socket, _errno) != 0) {
        return -1;
    }

    if (network_rt_wlan_socket_poll(_socket, POLLOUT, _errno) != 0) {
        return -1;
    }

    struct sockaddr_in addr;
    addr.sin_family = _socket->domain;
    addr.sin_port   = htons(port);
    memcpy(&addr.sin_addr, ip, MOD_NETWORK_IPADDR_BUF_SIZE);

    int ret = sendto(_socket->fileno, buf, len, 0, (struct sockaddr*)&addr, sizeof(addr));
    if (ret < 0) {
        *_errno = errno;
        // network_rt_wlan_socket_close(_socket);
        return -1;
    }
    return ret;
}

static mp_uint_t network_rt_wlan_socket_recvfrom(struct _mod_network_socket_obj_t* _socket, byte* buf, mp_uint_t len, byte* ip,
                                                 mp_uint_t* port, int* _errno)
{
    debug_printf("socket_recvfrom(%d), len %d\n", _socket->fileno, len);
    // Auto-bind the socket first if the socket is unbound.
    if (network_rt_wlan_socket_auto_bind(_socket, _errno) != 0) {
        return -1;
    }

    if (network_rt_wlan_socket_poll(_socket, POLLIN, _errno) != 0) {
        return -1;
    }

    struct sockaddr_in addr;
    socklen_t          server_addr_len = sizeof(addr);
    addr.sin_family                    = _socket->domain;

    *port = 0;

#if 0
    int ret = recvfrom(_socket->fileno, buf, len, 0, (struct sockaddr *)&addr, &server_addr_len);
    if (ret < 0) {
        *_errno = errno;
        debug_printf("socket_recvfrom() -> errno %d\n", *_errno);
        // network_rt_wlan_socket_close(_socket);

        if(EAGAIN == *_errno) {
            return 0;
        }

        return -1;
    }

    *port = ntohs(addr.sin_port);
    memcpy(ip, &addr.sin_addr.s_addr, sizeof(addr.sin_addr));

    return ret;
#else
    int       ret      = -1;
    mp_uint_t received = 0;

    mp_uint_t curr_tick_ms, stop_ms = 0;
    int32_t   timeout_ms = _socket->timeout;

    if (0 < timeout_ms) {
        stop_ms = mp_hal_ticks_ms() + timeout_ms;
    }

    do {
        *_errno = 0;
        MICROPY_EVENT_POLL_HOOK

        ret = recvfrom(_socket->fileno, buf + received, len - received, 0, (struct sockaddr*)&addr, &server_addr_len);

        if (0 > ret) {
            *_errno = errno;
            debug_printf("socket_recvfrom() -> errno %d\n", *_errno);

            if (EAGAIN == *_errno) {
                goto _check_timeout;
            }
            break;
        } else {
            received += ret;
        }

    _check_timeout:
        if (0x00 == timeout_ms) { // non blocking
            goto _exit;
        } else if ((-1) == timeout_ms) { // blocking
        } else {
            curr_tick_ms = mp_hal_ticks_ms();
            if (curr_tick_ms > stop_ms) {
                goto _exit;
            }
        }
    } while (received < len);

_exit:
    *port = ntohs(addr.sin_port);
    memcpy(ip, &addr.sin_addr.s_addr, sizeof(addr.sin_addr));

    return received;
#endif
}

static int network_rt_wlan_socket_setsockopt(struct _mod_network_socket_obj_t* _socket, mp_uint_t level, mp_uint_t opt,
                                             const void* optval, mp_uint_t optlen, int* _errno)
{
    debug_printf("socket_setsockopt(%d, %d)\n", _socket->fileno, opt);
    // if (opt == 20) {
    //     mp_sched_lock();
    //     socket->callback = (void *)optval;
    //     if (socket->callback != MP_OBJ_NULL) {
    //         mp_obj_list_append(MP_STATE_PORT(mp_wifi_sockpoll_list), socket);
    //     }
    //     mp_sched_unlock();
    //     return 0;
    // }
    int ret = setsockopt(_socket->fileno, level, opt, optval, optlen);
    if (ret < 0) {
        *_errno = errno;
        // network_rt_wlan_socket_close(_socket);
        debug_printf("socket_setsockopt() -> errno %d\n", *_errno);
        return -1;
    }
    return 0;
}

static int network_rt_wlan_socket_settimeout(struct _mod_network_socket_obj_t* _socket, mp_uint_t timeout_ms, int* _errno)
{
    int ret         = 0;
    int set_timeout = 1;

    (void)ret;

    debug_printf("socket_settimeout(%d, %d)\n", _socket->fileno, timeout_ms);

    if (0x00 == timeout_ms) {
        timeout_ms = 50;

        ret |= network_rt_wlan_socke_setblocking(_socket, false, _errno);
    } else if ((mp_uint_t)(-1) == timeout_ms) {
        timeout_ms = 50;

        // not set socket as blocking, we block in python.
        // ret |= network_rt_wlan_socke_setblocking(_socket, true, _errno);
    }

    if (set_timeout) {
        struct timeval timeout;
        timeout.tv_sec  = timeout_ms / 1000;
        timeout.tv_usec = (timeout_ms % 1000) * 1000;
        ret |= setsockopt(_socket->fileno, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
        ret |= setsockopt(_socket->fileno, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    }

    _socket->timeout = timeout_ms;

    if (ret < 0) {
        *_errno = errno;
        debug_printf("socket_settimeout() -> errno %d\n", *_errno);
    }

    return ret;
}

static int network_rt_wlan_socket_ioctl(struct _mod_network_socket_obj_t* _socket, mp_uint_t request, mp_uint_t arg,
                                        int* _errno)
{
    mp_uint_t ret = 0;
    debug_printf("socket_ioctl(%d, %d)\n", _socket->fileno, request);
    if (request == MP_STREAM_POLL) {
        fd_set         readfds, writefds;
        struct timeval tv = {
            .tv_sec  = 0,
            .tv_usec = 1000, // 1ms timeout
        };

        FD_ZERO(&readfds);
        FD_ZERO(&writefds);

        if (arg & MP_STREAM_POLL_RD) {
            FD_SET(_socket->fileno, &readfds);
        }

        if (arg & MP_STREAM_POLL_WR) {
            FD_SET(_socket->fileno, &writefds);
        }

        int nfds = _socket->fileno + 1;
        int res  = select(nfds, &readfds, &writefds, NULL, &tv);

        if (res < 0) {
            *_errno = errno;
            ret     = MP_STREAM_ERROR;
            debug_printf("socket_ioctl() -> errno %d\n", *_errno);
        } else {
            if ((arg & MP_STREAM_POLL_RD) && FD_ISSET(_socket->fileno, &readfds)) {
                ret |= MP_STREAM_POLL_RD;
            }
            if ((arg & MP_STREAM_POLL_WR) && FD_ISSET(_socket->fileno, &writefds)) {
                ret |= MP_STREAM_POLL_WR;
            }
        }
    } else {
        // NOTE: FIONREAD and FIONBIO are supported as well.
        *_errno = MP_EINVAL;
        ret     = MP_STREAM_ERROR;
    }
    return ret;
}

void network_rt_wlan_socket_deint(void)
{

}

const mod_network_nic_protocol_t mod_network_nic_protocol_rtt_posix = {
    // API for non-socket operations
    .gethostbyname = network_rt_wlan_socket_gethostbyname,
    .deinit = network_rt_wlan_socket_deint,

    // API for socket operations; return -1 on error
    .socket     = network_rt_wlan_socket_socket,
    .close      = network_rt_wlan_socket_close,
    .bind       = network_rt_wlan_socket_bind,
    .listen     = network_rt_wlan_socket_listen,
    .accept     = network_rt_wlan_socket_accept,
    .connect    = network_rt_wlan_socket_connect,
    .send       = network_rt_wlan_socket_send,
    .recv       = network_rt_wlan_socket_recv,
    .sendto     = network_rt_wlan_socket_sendto,
    .recvfrom   = network_rt_wlan_socket_recvfrom,
    .setsockopt = network_rt_wlan_socket_setsockopt,
    .settimeout = network_rt_wlan_socket_settimeout,
    .ioctl      = network_rt_wlan_socket_ioctl,
};
