#include "py/mphal.h"

#if MICROPY_PY_NETWORK

#include <string.h>
#include <stdio.h>
#include <stdarg.h>
#include <stdint.h>

#include <fcntl.h>
#include <errno.h>
#include <sys/time.h>
#include <sys/select.h>
#include <arpa/inet.h>
#include <netdb.h>

#include <unistd.h>    // For close()
#include <sys/ioctl.h>
#include <sys/types.h> // For socket types
#include <sys/socket.h>
#include <sys/select.h>
#include <poll.h>
#include <netinet/in.h> // For sockaddr_in

#include "py/obj.h"
#include "py/objtuple.h"
#include "py/objlist.h"
#include "py/stream.h"
#include "py/runtime.h"
#include "py/misc.h"
#include "py/mperrno.h"
#include "shared/netutils/netutils.h"
#include "extmod/modnetwork.h"
#include "mpprint.h"

#include "py_assert.h" // use openmv marco, PY_ASSERT_TYPE

#include "hal_netmgmt.h"

#define debug_printf(...) // mp_printf(&mp_plat_print, __VA_ARGS__)

// For auto-binding UDP sockets
#define BIND_PORT_RANGE_MIN     (65000)
#define BIND_PORT_RANGE_MAX     (65535)

static __attribute__((unused)) uint16_t bind_port = BIND_PORT_RANGE_MIN;

typedef struct _py_rt_net_obj_t {
    mp_obj_base_t base;
    enum rt_netif_t itf;
} py_rt_net_obj_t;

STATIC mp_obj_t network_rt_net_active(size_t n_args, const mp_obj_t *args) {
    py_rt_net_obj_t *self = MP_OBJ_TO_PTR(args[0]);

    if (n_args == 1) {
        int isactive = -1;
        enum rt_netif_t itf = self->itf;

        if(0x00 != netmgmt_utils_probe_device(itf, &isactive)) {
            mp_printf(&mp_plat_print, "run get isactive failed.\n");
            return mp_const_false;
        }
        return mp_obj_new_bool(0x00 != isactive);
    } else {
        mp_printf(&mp_plat_print, "Network (rt-smart) is always active and cannot be disabled.\n");

        return mp_const_none;
    }
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(network_rt_net_active_obj, 1, 2, network_rt_net_active);

STATIC mp_obj_t network_rt_net_ifconfig(size_t n_args, const mp_obj_t *args) {
    py_rt_net_obj_t *self = MP_OBJ_TO_PTR(args[0]);
    enum rt_netif_t itf = self->itf;
    struct ifconfig_t ifconfig;

    if (n_args == 1) {
        if(0x00 != netmgmt_utils_get_ifconfig(itf, &ifconfig)) {
            mp_printf(&mp_plat_print, "get ifconfig failed.\n");
            return mp_const_none;
        }

        mp_obj_t tuple[4] = {
            netutils_format_ipv4_addr((uint8_t *)&ifconfig.ip.addr, NETUTILS_BIG),
            netutils_format_ipv4_addr((uint8_t *)&ifconfig.netmask.addr, NETUTILS_BIG),
            netutils_format_ipv4_addr((uint8_t *)&ifconfig.gw.addr, NETUTILS_BIG),
            netutils_format_ipv4_addr((uint8_t *)&ifconfig.dns.addr, NETUTILS_BIG),
        };

        return mp_obj_new_tuple(4, tuple);
    } else {
        if (mp_obj_is_str(args[1])) {
            switch (mp_obj_str_get_qstr(args[1])) {
                case MP_QSTR_dhcp: {
                    if(0x00 != netmgmt_utils_set_ifconfig_dhcp(itf)) {
                        mp_printf(&mp_plat_print, "set ifconfig dhcp failed.\n");
                        return mp_const_false;
                    }
                } break;
                default: {
                    mp_raise_ValueError(MP_ERROR_TEXT("unknown config param"));
                } break;
            }
        } else {
            mp_obj_t *items;
            mp_obj_get_array_fixed_n(args[1], 4, &items);
            netutils_parse_ipv4_addr(items[0], (uint8_t *)&ifconfig.ip.addr, NETUTILS_BIG);
            netutils_parse_ipv4_addr(items[1], (uint8_t *)&ifconfig.netmask.addr, NETUTILS_BIG);
            netutils_parse_ipv4_addr(items[2], (uint8_t *)&ifconfig.gw.addr, NETUTILS_BIG);
            netutils_parse_ipv4_addr(items[3], (uint8_t *)&ifconfig.dns.addr, NETUTILS_BIG);

            if(0x00 != netmgmt_utils_set_ifconfig_static(itf, &ifconfig)) {
                mp_printf(&mp_plat_print, "set ifconfig static failed.\n");
                return mp_const_false;
            }
        }

        return mp_const_true;
    }
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(network_rt_net_ifconfig_obj, 1, 2, network_rt_net_ifconfig);

/* NIC Protocol **************************************************************/
STATIC void network_rt_wlan_socket_close(struct _mod_network_socket_obj_t *socket);
STATIC int network_rt_wlan_socket_settimeout(struct _mod_network_socket_obj_t *_socket, mp_uint_t timeout_ms, int *_errno);

// STATIC int network_rt_wlan_socket_get_error(mod_network_socket_obj_t *_socket) {
//     int optval;
//     socklen_t optlen = sizeof(optval);

//     if (getsockopt(_socket->fileno, SOL_SOCKET, SO_ERROR, &optval, &optlen) < 0) {
//         debug_printf("socket_getsockopt() -> errno %d\n", errno);
//         return -1;
//     }

//     return optval;
// }

STATIC int network_rt_wlan_socket_poll(mod_network_socket_obj_t *_socket, uint32_t rwf, int *_errno) {
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

STATIC int network_rt_wlan_socke_setblocking(mod_network_socket_obj_t *_socket, bool blocking, int *_errno) {
    int nonblocking = !blocking;
    // set socket in non-blocking mode
    if (ioctl(_socket->fileno, FIONBIO, &nonblocking) < 0) {
        *_errno = errno;
        network_rt_wlan_socket_close(_socket->fileno);
        return -1;
    }

    return 0;
}

STATIC int network_rt_wlan_socket_listening(mod_network_socket_obj_t *_socket, int *_errno) {
    int optval;
    socklen_t optlen = sizeof(optval);

    if (getsockopt(_socket->fileno, SOL_SOCKET, SO_ACCEPTCONN, &optval, &optlen) < 0) {
        *_errno = errno;
        debug_printf("socket_getsockopt() -> errno %d\n", errno);
        return -1;
    }

    return optval;
}

STATIC mp_uint_t network_rt_wlan_socket_auto_bind(mod_network_socket_obj_t *_socket, int *_errno) {
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

STATIC int network_rt_wlan_socket_gethostbyname(mp_obj_t nic, const char *name, mp_uint_t len, uint8_t *ip_out)
{
    if (len >= 256) {
        mp_printf(&mp_plat_print, "Host name length exceeds maximum of 255 bytes.\n");
        return -3;
    }

    // Make a null-terminated copy of hostname
    char hostname[256] = {0};
    memcpy(hostname, name, len);
    hostname[len] = '\0';

    struct hostent *he = gethostbyname(hostname);
    if (he == NULL || he->h_addrtype != AF_INET || he->h_length != 4) {
        mp_printf(&mp_plat_print, "Failed to resolve hostname: %s\n", hostname);
        return -1;
    }

    memcpy(ip_out, he->h_addr, 4);
    return 0;
}

// API for socket operations; return -1 on error
STATIC int network_rt_wlan_socket_socket(struct _mod_network_socket_obj_t *_socket, int *_errno)
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
    } else if(MOD_NETWORK_AF_INET6 == _socket->domain) {
        domain = AF_INET6;
    } else {
        *_errno = MP_EAFNOSUPPORT;
        return -1;
    }

    fd = socket(domain, type, _socket->proto);
    if (fd < 0) {
        *_errno = errno;
        mp_printf(&mp_plat_print,"socket_socket() -> errno %d\n", errno);
        return -1;
    }

    // set socket state
    _socket->fileno = fd;
    _socket->bound = false;
    _socket->callback = MP_OBJ_NULL;

    return network_rt_wlan_socke_setblocking(_socket, false, _errno);
}

STATIC void network_rt_wlan_socket_close(struct _mod_network_socket_obj_t *socket)
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

STATIC int network_rt_wlan_socket_bind(struct _mod_network_socket_obj_t *_socket, byte *ip, mp_uint_t port, int *_errno)
{
    debug_printf("socket_bind(%d, %d)\n", _socket->fileno, port);

    struct sockaddr_in addr;
    addr.sin_family = _socket->domain;
    addr.sin_port = htons(port);
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

STATIC int network_rt_wlan_socket_listen(struct _mod_network_socket_obj_t *_socket, mp_int_t backlog, int *_errno)
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

STATIC int network_rt_wlan_socket_accept(struct _mod_network_socket_obj_t *_socket,
    struct _mod_network_socket_obj_t *socket2, byte *ip, mp_uint_t *port, int *_errno)
{
    mp_uint_t curr_tick_ms, stop_ms = 0;
    int32_t timeout_ms = _socket->timeout;
    
    if(timeout_ms < 100){
        timeout_ms = 100;
    }

    if(0 < timeout_ms) {
        stop_ms = mp_hal_ticks_ms() + timeout_ms;
    }

    debug_printf("socket_accept(%d)\n", _socket->fileno);

    if (network_rt_wlan_socket_poll(_socket, POLLIN, _errno) != 0) {
        return -1;
    }
    
    if (network_rt_wlan_socke_setblocking(_socket, false, _errno) != 0) {
        return -1;
    }

    struct sockaddr_in addr;
    int addrlen = sizeof(addr);
    addr.sin_family = _socket->domain;

    *port = 0;
    int fd = -1;
    do {
        *_errno = 0;
        MICROPY_EVENT_POLL_HOOK

        fd = accept(_socket->fileno, (struct sockaddr*)&addr, (socklen_t*)&addrlen);
        if(0 > fd) {
            *_errno = errno;

            debug_printf("socket_accept() -> errno %d %d\n", *_errno, fd);

            if(EAGAIN == *_errno) {
                goto _check_timeout;
            }

            return -1;
        }

_check_timeout:
        if(0x00 == timeout_ms) { // non blocking
            *_errno = EAGAIN;
            return -1;
        } else if((-1) == timeout_ms) { // blocking
        } else {
            curr_tick_ms = mp_hal_ticks_ms();
            if(curr_tick_ms > stop_ms) {
                *_errno = EAGAIN;
                return -1;
            }
        }
    } while(0 > fd);

    *port = ntohs(addr.sin_port);
    memcpy(ip, &addr.sin_addr.s_addr, sizeof(addr.sin_addr));

    // set socket state
    socket2->fileno = fd;
    socket2->bound = false;
    socket2->callback = MP_OBJ_NULL;

    return network_rt_wlan_socket_settimeout(_socket, _socket->timeout, _errno);
}

STATIC int network_rt_wlan_socket_connect(struct _mod_network_socket_obj_t *_socket, byte *ip, mp_uint_t port, int *_errno)
{
    debug_printf("socket_connect(%d)\n", _socket->fileno);
    
    struct sockaddr_in addr;
    addr.sin_family = _socket->domain;
    addr.sin_port = htons(port);
    memcpy(&addr.sin_addr, ip, MOD_NETWORK_IPADDR_BUF_SIZE);
    
    int ret = -1;
    
    mp_uint_t curr_tick_ms, stop_ms = 0;
    int32_t timeout_ms = _socket->timeout;

    if(0 < timeout_ms) {
        stop_ms = mp_hal_ticks_ms() + timeout_ms;
    }

    if (network_rt_wlan_socke_setblocking(_socket, false, _errno) != 0) {
        return -1;
    }

    do{
        MICROPY_EVENT_POLL_HOOK
        ret = connect(_socket->fileno, (struct sockaddr *)&addr, sizeof(addr));
        if(0 == ret){
            break;
        }
        *_errno = errno;
        debug_printf("socket_connect() -> errno %d %d\n", *_errno, ret);

        switch (*_errno) {
            case EINPROGRESS:
            case EALREADY:{
                *_errno = EAGAIN;
                goto _check_timeout;
            }
            
            case ENOTCONN:
            default:{
                mp_printf(&mp_plat_print, "connect to server faild!\n");
                return -1;
            }
        }
        
_check_timeout:
        if(0x00 == timeout_ms) { // non blocking
            debug_printf("socket_connect() -> non blocking\n");
            return -1;
        } else if((-1) == timeout_ms) { // blocking
        } else {
            curr_tick_ms = mp_hal_ticks_ms();
            if(curr_tick_ms > stop_ms) {
                debug_printf("socket_connect() -> timeout\n");
                mp_printf(&mp_plat_print, "connect timeout\n");
                *_errno = ETIMEDOUT;
                return -1;
            }
        }
        debug_printf("retryng...\n");
    }while(ret < 0);

    network_rt_wlan_socket_settimeout(_socket, _socket->timeout, _errno);
    mp_printf(&mp_plat_print, "connect success\n");

    return 0;
}

STATIC mp_uint_t network_rt_wlan_socket_send(struct _mod_network_socket_obj_t *_socket, const byte *buf, mp_uint_t len, int *_errno)
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

STATIC mp_uint_t network_rt_wlan_socket_recv(struct _mod_network_socket_obj_t *_socket, byte *buf, mp_uint_t len, int *_errno)
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
    int ret = -1;
    mp_uint_t received = 0;

    mp_uint_t curr_tick_ms, stop_ms = 0;
    int32_t timeout_ms = _socket->timeout;

    if(0 < timeout_ms) {
        stop_ms = mp_hal_ticks_ms() + timeout_ms;
    }

    do {
        *_errno = 0;
        MICROPY_EVENT_POLL_HOOK

        ret = recv(_socket->fileno, buf + received, len - received, 0);

        if(0 > ret) {
            *_errno = errno;

            debug_printf("socket_recv() -> errno %d %d\n", *_errno, ret);

            if(EAGAIN == *_errno) {
                goto _check_timeout;
            }
            break;
        } else {
            received += ret;
        }

_check_timeout:
        if(0x00 == timeout_ms) { // non blocking
            return received;
        } else if((-1) == timeout_ms) { // blocking
        } else {
            curr_tick_ms = mp_hal_ticks_ms();
            if(curr_tick_ms > stop_ms) {
                printf("recv timeout!\n");
                return received;
            }
        }
    } while(received < len);

    return received;
#endif
}

STATIC mp_uint_t network_rt_wlan_socket_sendto(struct _mod_network_socket_obj_t *_socket, const byte *buf, mp_uint_t len, byte *ip, mp_uint_t port, int *_errno)
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
    addr.sin_port = htons(port);
    memcpy(&addr.sin_addr, ip, MOD_NETWORK_IPADDR_BUF_SIZE);

    int ret = sendto(_socket->fileno, buf, len, 0, (struct sockaddr *)&addr, sizeof(addr));
    if (ret < 0) {
        *_errno = errno;
        // network_rt_wlan_socket_close(_socket);
        return -1;
    }
    return ret;
}

STATIC mp_uint_t network_rt_wlan_socket_recvfrom(struct _mod_network_socket_obj_t *_socket, byte *buf, mp_uint_t len, byte *ip, mp_uint_t *port, int *_errno)
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
    socklen_t server_addr_len = sizeof(addr);
    addr.sin_family = _socket->domain;

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
    int ret = -1;
    mp_uint_t received = 0;

    mp_uint_t curr_tick_ms, stop_ms = 0;
    int32_t timeout_ms = _socket->timeout;

    if(0 < timeout_ms) {
        stop_ms = mp_hal_ticks_ms() + timeout_ms;
    }

    do {
        *_errno = 0;
        MICROPY_EVENT_POLL_HOOK

        ret = recvfrom(_socket->fileno, buf + received, len - received, 0, (struct sockaddr *)&addr, &server_addr_len);

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
        if(0x00 == timeout_ms) { // non blocking
            goto _exit;
        } else if((-1) == timeout_ms) { // blocking
        } else {
            curr_tick_ms = mp_hal_ticks_ms();
            if(curr_tick_ms > stop_ms) {
                mp_printf(&mp_plat_print, "recvfrom timeout!\n");
                goto _exit;
            }
        }
    } while(received < len);

_exit:
    *port = ntohs(addr.sin_port);
    memcpy(ip, &addr.sin_addr.s_addr, sizeof(addr.sin_addr));

    return received;
#endif
}

STATIC int network_rt_wlan_socket_setsockopt(struct _mod_network_socket_obj_t *_socket, mp_uint_t level, mp_uint_t opt, const void *optval, mp_uint_t optlen, int *_errno)
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

STATIC int network_rt_wlan_socket_settimeout(struct _mod_network_socket_obj_t *_socket, mp_uint_t timeout_ms, int *_errno)
{
    int ret = 0;

    (void)ret;
    
    debug_printf("socket_settimeout(%d, %d)\n", _socket->fileno, timeout_ms);
    

    if (0x00 == timeout_ms) {
        _socket->timeout = 0;
        
        ret |= network_rt_wlan_socke_setblocking(_socket, false, _errno);
    } else{
        _socket->timeout = timeout_ms;

        if ((timeout_ms > 500) || (timeout_ms < 0)){
            timeout_ms = 500;
        }
        
        ret |= network_rt_wlan_socke_setblocking(_socket, true, _errno);

        debug_printf("socket_settimeout_opt(%d, %d)\n", _socket->fileno, timeout_ms);
        struct timeval timeout;
        timeout.tv_sec = timeout_ms / 1000;
        timeout.tv_usec = (timeout_ms % 1000) * 1000;
        ret |= setsockopt(_socket->fileno, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
        ret |= setsockopt(_socket->fileno, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    }

    if (ret < 0) {
        *_errno = errno;
        debug_printf("socket_settimeout() -> errno %d\n", *_errno);
    }
    
    return ret;
}

STATIC int network_rt_wlan_socket_ioctl(struct _mod_network_socket_obj_t *_socket, mp_uint_t request, mp_uint_t arg, int *_errno) {
    mp_uint_t ret = 0;
    debug_printf("socket_ioctl(%d, %d)\n", _socket->fileno, request);
    if (request == MP_STREAM_POLL) {
        fd_set readfds, writefds;
        struct timeval tv = {
            .tv_sec = 0,
            .tv_usec = 1000,  // 1ms timeout
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
        int res = select(nfds, &readfds, &writefds, NULL, &tv);

        if (res < 0) {
            *_errno = errno;
            ret = MP_STREAM_ERROR;
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
        ret = MP_STREAM_ERROR;
    }
    return ret;
}

STATIC const mod_network_nic_protocol_t mod_network_nic_protocol_rtt_posix = {
    // API for non-socket operations
    .gethostbyname = network_rt_wlan_socket_gethostbyname,

    // API for socket operations; return -1 on error
    .socket = network_rt_wlan_socket_socket,
    .close = network_rt_wlan_socket_close,
    .bind = network_rt_wlan_socket_bind,
    .listen = network_rt_wlan_socket_listen,
    .accept = network_rt_wlan_socket_accept,
    .connect = network_rt_wlan_socket_connect,
    .send = network_rt_wlan_socket_send,
    .recv = network_rt_wlan_socket_recv,
    .sendto = network_rt_wlan_socket_sendto,
    .recvfrom = network_rt_wlan_socket_recvfrom,
    .setsockopt = network_rt_wlan_socket_setsockopt,
    .settimeout = network_rt_wlan_socket_settimeout,
    .ioctl = network_rt_wlan_socket_ioctl,
};

#ifdef CONFIG_ENABLE_NETWORK_RT_LAN_OVER_USB
/* network_rt_lan ************************************************************/
STATIC mp_obj_t network_rt_lan_isconnected(mp_obj_t self_in) {
    py_rt_net_obj_t *self = MP_OBJ_TO_PTR(self_in);
    (void)self;

    int isconnected = 0;
    if(0x00 != netmgmt_lan_get_isconnected(self->itf, &isconnected)) {
        mp_printf(&mp_plat_print, "run get isconnected failed.\n");
        return mp_const_false;
    }
    return mp_obj_new_bool(0x00 != isconnected);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(network_rt_lan_isconnected_obj, network_rt_lan_isconnected);

STATIC mp_obj_t network_rt_lan_status(size_t n_args, const mp_obj_t *args) {
    py_rt_net_obj_t *self = MP_OBJ_TO_PTR(args[0]);
    (void)self;

    if (n_args == 1) {
        int status = 0;

        if(0x00 != netmgmt_lan_get_link_status(self->itf, &status)) {
            status = 0; // failed

            mp_printf(&mp_plat_print, "run get status failed.\n");
        }
        return MP_OBJ_NEW_SMALL_INT(status);
    }
    mp_raise_ValueError(MP_ERROR_TEXT("unknown status param"));
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(network_rt_lan_status_obj, 1, 2, network_rt_lan_status);

STATIC mp_obj_t network_rt_lan_config(size_t n_args, const mp_obj_t *args, mp_map_t *kwargs) {
    py_rt_net_obj_t *self = MP_OBJ_TO_PTR(args[0]);
    (void)self;

    if (kwargs->used == 0) {
        // Get config value
        if (n_args != 2) {
            mp_raise_TypeError(MP_ERROR_TEXT("must query one param"));
        }

        switch (mp_obj_str_get_qstr(args[1])) {
            case MP_QSTR_mac: {
                uint8_t buf[6];

                if(0x00 != netmgmt_lan_get_mac(self->itf, &buf[0])) {
                    memset(&buf[0], 0, sizeof(buf)); // failed

                    mp_printf(&mp_plat_print, "run get mac failed.\n");
                }

                return mp_obj_new_bytes(buf, 6);
            }
            default:
                mp_raise_ValueError(MP_ERROR_TEXT("unknown config param"));
        }
    } else {
        // Set config value(s)
        if (n_args != 1) {
            mp_raise_TypeError(MP_ERROR_TEXT("can't specify pos and kw args"));
        }

        for (size_t i = 0; i < kwargs->alloc; ++i) {
            if (MP_MAP_SLOT_IS_FILLED(kwargs, i)) {
                mp_map_elem_t *e = &kwargs->table[i];
                switch (mp_obj_str_get_qstr(e->key)) {
                    case MP_QSTR_mac: {
                        mp_buffer_info_t buf;
                        mp_get_buffer_raise(e->value, &buf, MP_BUFFER_READ);
                        if (buf.len != 6) {
                            mp_raise_ValueError(NULL);
                        }
                        
                        if(0x00 != netmgmt_lan_set_mac(self->itf, buf.buf)) {
                            mp_printf(&mp_plat_print, "run set mac failed.\n");
                        }

                        break;
                    }
                    default:
                        mp_raise_ValueError(MP_ERROR_TEXT("unknown config param"));
                }
            }
        }

        return mp_const_none;
    }
}
STATIC MP_DEFINE_CONST_FUN_OBJ_KW(network_rt_lan_config_obj, 1, network_rt_lan_config);

const struct _mp_obj_type_t network_type_eth_lan;

STATIC py_rt_net_obj_t network_rt_eth_lan = {{(mp_obj_type_t *)&network_type_eth_lan}, RT_NET_DEV_USB_RTL8152};
STATIC py_rt_net_obj_t network_rt_eth_lte = {{(mp_obj_type_t *)&network_type_eth_lan}, RT_NET_DEV_USB_ECM};

STATIC mp_obj_t py_rt_eth_lan_type_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *all_args) {
    enum { ARG_itf };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_itf, MP_ARG_INT, {.u_int = RT_NET_DEV_USB_RTL8152} },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all_kw_array(n_args, n_kw, all_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    mp_obj_t rt_net_obj;

    if(RT_NET_DEV_USB_RTL8152 == args[ARG_itf].u_int) {
        rt_net_obj = MP_OBJ_FROM_PTR(&network_rt_eth_lan);
    } else if(RT_NET_DEV_USB_ECM == args[ARG_itf].u_int) {
        rt_net_obj = MP_OBJ_FROM_PTR(&network_rt_eth_lte);
    } else {
        mp_raise_TypeError(MP_ERROR_TEXT("Unsupport type"));
    }

    // Register with network module
    mod_network_register_nic(rt_net_obj);

    return rt_net_obj;
}

STATIC const mp_rom_map_elem_t network_type_lan_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR_active), MP_ROM_PTR(&network_rt_net_active_obj) },
    { MP_ROM_QSTR(MP_QSTR_isconnected), MP_ROM_PTR(&network_rt_lan_isconnected_obj) },
    { MP_ROM_QSTR(MP_QSTR_status), MP_ROM_PTR(&network_rt_lan_status_obj) },
    { MP_ROM_QSTR(MP_QSTR_ifconfig), MP_ROM_PTR(&network_rt_net_ifconfig_obj) },
    { MP_ROM_QSTR(MP_QSTR_config), MP_ROM_PTR(&network_rt_lan_config_obj) },
};
STATIC MP_DEFINE_CONST_DICT(network_type_lan_locals_dict, network_type_lan_locals_dict_table);

MP_DEFINE_CONST_OBJ_TYPE(
    network_type_eth_lan,
    MP_QSTR_eth_lan,
    MP_TYPE_FLAG_NONE,
    make_new, py_rt_eth_lan_type_make_new,
    locals_dict, &network_type_lan_locals_dict,
    protocol, &mod_network_nic_protocol_rtt_posix
    );

#endif // CONFIG_ENABLE_NETWORK_RT_LAN_OVER_USB

#ifdef CONFIG_ENABLE_NETWORK_RT_WLAN
/* rt_wlan_info **************************************************************/
STATIC const mp_obj_type_t py_rt_wlan_info_type;

typedef struct _py_rt_wlan_info_obj_t {
    mp_obj_base_t base;
    struct rt_wlan_info_t _cobj;
} py_rt_wlan_info_obj_t;

STATIC const char *rt_wlan_security_string(enum rt_wlan_security_t security)
{
    switch (security) {
        case SECURITY_OPEN: return "SECURITY_OPEN";
        case SECURITY_WEP_PSK: return "SECURITY_WEP_PSK";
        case SECURITY_WEP_SHARED: return "SECURITY_WEP_SHARED";
        case SECURITY_WPA_TKIP_PSK: return "SECURITY_WPA_TKIP_PSK";
        case SECURITY_WPA_TKIP_8021X: return "SECURITY_WPA_TKIP_8021X";
        case SECURITY_WPA_AES_PSK: return "SECURITY_WPA_AES_PSK";
        case SECURITY_WPA_AES_8021X: return "SECURITY_WPA_AES_8021X";
        case SECURITY_WPA2_AES_PSK: return "SECURITY_WPA2_AES_PSK";
        case SECURITY_WPA2_AES_8021X: return "SECURITY_WPA2_AES_8021X";
        case SECURITY_WPA2_TKIP_PSK: return "SECURITY_WPA2_TKIP_PSK";
        case SECURITY_WPA2_TKIP_8021X: return "SECURITY_WPA2_TKIP_8021X";
        case SECURITY_WPA2_MIXED_PSK: return "SECURITY_WPA2_MIXED_PSK";
        case SECURITY_WPA_WPA2_MIXED_PSK: return "SECURITY_WPA_WPA2_MIXED_PSK";
        case SECURITY_WPA_WPA2_MIXED_8021X: return "SECURITY_WPA_WPA2_MIXED_8021X";
        case SECURITY_WPA2_AES_CMAC: return "SECURITY_WPA2_AES_CMAC";
        case SECURITY_WPS_OPEN: return "SECURITY_WPS_OPEN";
        case SECURITY_WPS_SECURE: return "SECURITY_WPS_SECURE";
        case SECURITY_WPA3_AES_PSK: return "SECURITY_WPA3_AES_PSK";
        default: return "UNKNOWN";
    }

    return NULL;
}

STATIC const char *rt_wlan_band_string(enum rt_802_11_band_t band)
{
    switch(band) {
        case RT_802_11_BAND_5GHZ: return "5G";
        case RT_802_11_BAND_2_4GHZ: return "2.4G";
        default: return "UNKNOWN";
    }

    return NULL;
}

STATIC mp_obj_t py_rt_wlan_info_from_struct(struct rt_wlan_info_t *info)
{
    py_rt_wlan_info_obj_t *o = m_new_obj_with_finaliser(py_rt_wlan_info_obj_t);
    o->base.type = &py_rt_wlan_info_type;
    o->_cobj = *info;
    return o;
}

STATIC mp_obj_t py_rt_wlan_info_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *all_args) {
    enum { ARG_ssid, ARG_bssid, ARG_channel, ARG_security, ARG_band, ARG_hidden };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_ssid,         MP_ARG_OBJ, {.u_obj = mp_const_none} },
        { MP_QSTR_bssid,        MP_ARG_OBJ, {.u_obj = mp_const_none} },
        { MP_QSTR_channel,      MP_ARG_INT, {.u_int = 1} },
        { MP_QSTR_rssi,         MP_ARG_INT, {.u_int = -99} },
        { MP_QSTR_security,     MP_ARG_INT, {.u_int = SECURITY_OPEN} },
        { MP_QSTR_band,         MP_ARG_INT, {.u_int = RT_802_11_BAND_2_4GHZ} },
        { MP_QSTR_hidden,       MP_ARG_INT, {.u_int = 0} },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all_kw_array(n_args, n_kw, all_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    struct rt_wlan_info_t info;
    memset(&info, 0, sizeof(info));

    if(mp_const_none != args[ARG_ssid].u_obj) {
        const char *ssid = mp_obj_str_get_str(args[ARG_ssid].u_obj);
        int ssid_len = strlen(ssid);
        if ((0x00 == ssid_len) || (RT_WLAN_SSID_MAX_LENGTH < ssid_len)) {
            mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("SSID can't be empty, and can't longer than %d"), RT_WLAN_SSID_MAX_LENGTH);
        }
        strncpy((char *)info.ssid.val, ssid, RT_WLAN_SSID_MAX_LENGTH);
        info.ssid.len = strlen(ssid);
    }

    if(mp_const_none != args[ARG_bssid].u_obj) {
        uint8_t bssid[RT_WLAN_BSSID_MAX_LENGTH];
        mp_obj_t *items;
        mp_obj_get_array_fixed_n(args[ARG_bssid].u_obj, RT_WLAN_BSSID_MAX_LENGTH, &items);
        for(int i = 0; i < RT_WLAN_BSSID_MAX_LENGTH; i++) {
            bssid[i] = (uint8_t)mp_obj_get_int(items[i]);
        }
        memcpy(&info.bssid[0], bssid, RT_WLAN_BSSID_MAX_LENGTH);
    }

    info.channel = args[ARG_channel].u_int;
    info.security = args[ARG_security].u_int;
    info.band = args[ARG_band].u_int;
    info.hidden = args[ARG_hidden].u_int;

    return py_rt_wlan_info_from_struct(&info);
}

STATIC void *py_rt_wlan_info_cobj(mp_obj_t rt_wlan_info) {
    PY_ASSERT_TYPE(rt_wlan_info, &py_rt_wlan_info_type);
    return &((py_rt_wlan_info_obj_t *) rt_wlan_info)->_cobj;
}

STATIC void py_rt_wlan_info_print(const mp_print_t *print, mp_obj_t self_in, mp_print_kind_t kind) {
    py_rt_wlan_info_obj_t *self = self_in;
    struct rt_wlan_info_t *info = py_rt_wlan_info_cobj(self);

    mp_printf(print,
              "{\"ssid\":\"%s\", \"bssid\":%02X:%02X:%02X:%02X:%02X:%02X, \"channel\":%d, \"rssi\":%d, \"security\":\"%s\", \"band\":\"%s\", \"hidden\":%d}",
              info->ssid.val, \
              info->bssid[0], info->bssid[1], info->bssid[2], \
              info->bssid[3], info->bssid[4], info->bssid[5], \
              info->channel, info->rssi, rt_wlan_security_string(info->security), rt_wlan_band_string(info->band), info->hidden);
}

STATIC void py_rt_wlan_info_attr(mp_obj_t self_in, qstr attr, mp_obj_t *dest) {
    py_rt_wlan_info_obj_t *self = self_in;
    struct rt_wlan_info_t *info = py_rt_wlan_info_cobj(self);

    if(MP_OBJ_NULL == dest[0]) {
        // load attribute
        switch(attr) {
            case MP_QSTR_ssid:
                dest[0] = mp_obj_new_bytes(info->ssid.val, info->ssid.len);
                break;
            case MP_QSTR_bssid:
                dest[0] = mp_obj_new_bytes(info->bssid, RT_WLAN_BSSID_MAX_LENGTH);
                break;
            case MP_QSTR_channel:
                dest[0] = MP_OBJ_NEW_SMALL_INT(info->channel);
                break;
            case MP_QSTR_rssi:
                dest[0] = MP_OBJ_NEW_SMALL_INT(info->rssi);
                break;
            case MP_QSTR_security:
                dest[0] = MP_OBJ_NEW_SMALL_INT(info->security);
                break;
            case MP_QSTR_band:
                dest[0] = MP_OBJ_NEW_SMALL_INT(info->band);
                break;
            case MP_QSTR_hidden:
                dest[0] = MP_OBJ_NEW_SMALL_INT(info->hidden);
                break;
            default:
                dest[1] = MP_OBJ_SENTINEL; // continue lookup in locals_dict
                break;
        }
    } else if(MP_OBJ_SENTINEL == dest[0]) {
        // store attribute
        switch(attr) {
            case MP_QSTR_ssid:
                const char *ssid = mp_obj_str_get_str(dest[1]);

                strncpy((char *)info->ssid.val, ssid, RT_WLAN_SSID_MAX_LENGTH);
                info->ssid.len = strlen(ssid);
                break;
            case MP_QSTR_bssid:
                uint8_t bssid[RT_WLAN_BSSID_MAX_LENGTH];
                mp_obj_t *items;
                mp_obj_get_array_fixed_n(dest[1], RT_WLAN_BSSID_MAX_LENGTH, &items);
                for(int i = 0; i < RT_WLAN_BSSID_MAX_LENGTH; i++) {
                    bssid[i] = (uint8_t)mp_obj_get_int(items[i]);
                }
                memcpy(info->bssid, bssid, RT_WLAN_BSSID_MAX_LENGTH);
                break;
            case MP_QSTR_channel:
                info->channel = MP_OBJ_SMALL_INT_VALUE(dest[1]);
                break;
            case MP_QSTR_rssi:
                info->rssi = MP_OBJ_SMALL_INT_VALUE(dest[1]);
                break;
            case MP_QSTR_security:
                info->security = MP_OBJ_SMALL_INT_VALUE(dest[1]);
                break;
            case MP_QSTR_band:
                info->band = MP_OBJ_SMALL_INT_VALUE(dest[1]);
                break;
            case MP_QSTR_hidden:
                info->hidden = MP_OBJ_SMALL_INT_VALUE(dest[1]);
                break;
            default:
                // not support set, directly return
                return;
        }
        dest[0] = MP_OBJ_NULL;
    }
}

STATIC MP_DEFINE_CONST_OBJ_TYPE(
    py_rt_wlan_info_type,
    MP_QSTR_rt_wlan_info,
    MP_TYPE_FLAG_NONE,
    make_new, py_rt_wlan_info_make_new,
    print, py_rt_wlan_info_print,
    attr, py_rt_wlan_info_attr
);

/* network_rt_wlan ***********************************************************/
STATIC mp_obj_t network_rt_wlan_scan(size_t n_args, const mp_obj_t *args) {
    py_rt_net_obj_t *self = MP_OBJ_TO_PTR(args[0]);
    mp_obj_t scan_list;

    int ap_num = -1, result = -1;
    struct rt_wlan_info_t ap_infos[RT_WLAN_STA_SCAN_MAX_AP];
    const char *ssid = NULL;

    if(MOD_NETWORK_STA_IF != self->itf) {
        mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("ap mode not support scan"));
    }

    if(0x02 == n_args) {
        ssid = mp_obj_str_get_str(args[1]);
        if(0x00 == strlen(ssid)) {
            ssid = NULL;
        }
    }

    if(ssid) {
        ap_num = 1;
        result = netmgmt_wlan_sta_scan_with_ssid((char *)ssid, ap_infos);
    } else {
        result = netmgmt_wlan_sta_scan(&ap_num, ap_infos);
    }

    if(0x00 != result) {
        ap_num = 0;
        mp_printf(&mp_plat_print, "run scan failed.\n");
    }
    scan_list = mp_obj_new_list(0, NULL);

    for(int32_t i = 0; i < ap_num; i++) {
        mp_obj_t info = py_rt_wlan_info_from_struct(&ap_infos[i]);
        mp_obj_list_append(scan_list, info);
    }

    return scan_list;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(network_rt_wlan_scan_obj, 1, 2, network_rt_wlan_scan);

STATIC mp_obj_t network_rt_wlan_connect(mp_uint_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    py_rt_net_obj_t *self = MP_OBJ_TO_PTR(pos_args[0]);

    enum { ARG_ssid, ARG_key, ARG_info };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_ssid,     MP_ARG_OBJ, {.u_obj = mp_const_none} },
        { MP_QSTR_key,      MP_ARG_OBJ, {.u_obj = mp_const_none} },
        { MP_QSTR_info,     MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_obj = mp_const_none} },
    };

    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args - 1, pos_args + 1, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    int use_info = 0, result = -1;
    struct rt_wlan_info_t info;
    const char *ssid = NULL;

    if (mp_const_none != args[ARG_ssid].u_obj) {
        use_info = 0x00;

        ssid = mp_obj_str_get_str(args[ARG_ssid].u_obj);
        int ssid_len = strlen(ssid);
        if ((0x00 == ssid_len) || (RT_WLAN_SSID_MAX_LENGTH < ssid_len)) {
            mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("SSID can't be empty, and can't longer than %d"), RT_WLAN_SSID_MAX_LENGTH);
        }
    } else if (mp_const_none != args[ARG_info].u_obj) {
        use_info = 1;

        struct rt_wlan_info_t *_info = py_rt_wlan_info_cobj(args[ARG_info].u_obj);
        memcpy(&info, _info, sizeof(struct rt_wlan_info_t));
    } else {
        mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("should set ssid or ap"));
    }

    int key_len = 0;
    const char *key = NULL;
    if (mp_const_none != args[ARG_key].u_obj) {
        key = mp_obj_str_get_str(args[ARG_key].u_obj);
        key_len = strlen(key);

        if((0x08 > key_len) || (RT_WLAN_PASSWORD_MAX_LENGTH < key_len)) {
            mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("Key length(%d) should be 8 - %d"), key_len, RT_WLAN_PASSWORD_MAX_LENGTH);
        }
    }

    if(MOD_NETWORK_STA_IF == self->itf) {
        if(0x00 == use_info) {
            result = netmgmt_wlan_sta_connect_with_ssid((char *)ssid, (char *)key);
        } else {
            result = netmgmt_wlan_sta_connect_with_scan_info(&info, (char *)key);
        }

        if(0x00 != result) {
            mp_printf(&mp_plat_print, "run connect failed.\n");
            return mp_const_false;
        }
    } else {
        if(0x00 == use_info) {
            result = netmgmt_wlan_ap_start_with_ssid((char *)ssid, (char *)key);
        } else {
            result = netmgmt_wlan_ap_start_with_info(&info, (char *)key);
        }

        if(0x00 != result) {
            mp_printf(&mp_plat_print, "start ap failed.\n");
            return mp_const_false;
        }
    }

    return mp_const_true;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_KW(network_rt_wlan_connect_obj, 1, network_rt_wlan_connect);

STATIC mp_obj_t network_rt_wlan_disconnect(size_t n_args, const mp_obj_t *args) {
    py_rt_net_obj_t *self = MP_OBJ_TO_PTR(args[0]);

    if(MOD_NETWORK_STA_IF == self->itf) {
        if(0x00 != netmgmt_wlan_sta_disconnect_ap()) {
            mp_printf(&mp_plat_print, "run disconnect failed.\n");
            return mp_const_false;
        }
    } else {
        uint8_t mac[6];
        mp_obj_t *items;
        mp_obj_get_array_fixed_n(args[1], 6, &items);
        for(int i = 0; i < 6; i++) {
            mac[i] = (uint8_t)mp_obj_get_int(items[i]);
        }

        if(0x00 != netmgmt_wlan_ap_disconnect_sta(mac)) {
            mp_printf(&mp_plat_print, "run ap deauth failed.\n");
            return mp_const_false;
        }
    }

    return mp_const_true;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(network_rt_wlan_disconnect_obj, 1, 2, network_rt_wlan_disconnect);

STATIC mp_obj_t network_rt_wlan_isconnected(mp_obj_t self_in) {
    py_rt_net_obj_t *self = MP_OBJ_TO_PTR(self_in);
    int status = -1;

    if(MOD_NETWORK_STA_IF != self->itf) {
        mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("ap mode not support connect"));
    }

    if(0x00 != netmgmt_wlan_sta_isconnected(&status)) {
        status = false;
        mp_printf(&mp_plat_print, "run isconnected failed.\n");
    }

    return mp_obj_new_bool(status);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(network_rt_wlan_isconnected_obj, network_rt_wlan_isconnected);

STATIC mp_obj_t _network_rt_wlan_sta_config(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args)
{
    // py_rt_net_obj_t *self = MP_OBJ_TO_PTR(pos_args[0]);

    if (kw_args->used == 0) {
        // Get config value
        if (n_args != 2) {
            mp_raise_TypeError(MP_ERROR_TEXT("must query one param.\n"));
        }
        qstr attr = mp_obj_str_get_qstr(pos_args[1]);

        switch(attr) {
            case MP_QSTR_mac: {
                uint8_t mac[6];
                
                if(0x00 != netmgmt_wlan_sta_get_mac(&mac[0])) {
                    mp_printf(&mp_plat_print, "run get mac failed.\n");
                    return mp_const_none;
                }

                return mp_obj_new_bytes(mac, sizeof(mac));
            } break;
            case MP_QSTR_auto_reconnect: {
                int auto_reconnect = 0;

                if(0x00 != netmgmt_wlan_sta_get_auto_reconnect(&auto_reconnect)) {
                    auto_reconnect = 0;
                    mp_printf(&mp_plat_print, "run get auto reconnect failed.\n");
                }
                return mp_obj_new_bool(auto_reconnect);
            } break;
        }
    } else {
        enum { ARG_mac, ARG_auto_reconnect };
        static const mp_arg_t allowed_args[] = {
            { MP_QSTR_mac,                  MP_ARG_OBJ, {.u_obj = mp_const_none} },
            { MP_QSTR_auto_reconnect,       MP_ARG_OBJ, {.u_obj = mp_const_none} },
        };
        mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
        mp_arg_parse_all(n_args - 1, pos_args + 1, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

        if(mp_const_none != args[ARG_mac].u_obj) {
            uint8_t mac[6];
            mp_obj_t *items;
            mp_obj_get_array_fixed_n(args[ARG_mac].u_obj, 6, &items);
            for(int i = 0; i < 6; i++) {
                mac[i] = (uint8_t)mp_obj_get_int(items[i]);
            }

            if(0x00 != netmgmt_wlan_sta_set_mac(&mac[0])) {
                mp_printf(&mp_plat_print, "run set mac failed.\n");
                return mp_const_false;
            }
        }

        if(mp_const_none != args[ARG_auto_reconnect].u_obj) {
            int auto_reconnect = 0;

            if(mp_obj_is_true(args[ARG_auto_reconnect].u_obj)) {
                auto_reconnect = 1;
            }

            if(0x00 != netmgmt_wlan_sta_set_auto_reconnect(auto_reconnect)) {
                mp_printf(&mp_plat_print, "run set auto_reconnect failed.\n");
                return mp_const_false;
            }
        }
    }

    return mp_const_true;
}

STATIC mp_obj_t _network_rt_wlan_ap_get_info(mp_obj_t self_in)
{
    py_rt_net_obj_t *self = MP_OBJ_TO_PTR(self_in);

    if(MOD_NETWORK_AP_IF != self->itf) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("only ap if can get info"));
    }

    struct rt_wlan_info_t info;
    
    if(0x00 != netmgmt_wlan_ap_get_info(&info)) {
        mp_printf(&mp_plat_print, "run get ap info failed.\n");
        return mp_const_none;
    }

    return py_rt_wlan_info_from_struct(&info);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(network_rt_wlan_ap_get_info_obj, _network_rt_wlan_ap_get_info);

STATIC mp_obj_t _network_rt_wlan_ap_config(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args)
{
    // py_rt_net_obj_t *self = MP_OBJ_TO_PTR(args[0]);

    if (kw_args->used == 0) {
        // Get config value
        if (n_args != 2) {
            mp_raise_TypeError(MP_ERROR_TEXT("must query one param"));
        }
        qstr attr = mp_obj_str_get_qstr(pos_args[1]);

        switch(attr) {
            case MP_QSTR_info: {
                return _network_rt_wlan_ap_get_info(pos_args[0]);
            } break;
            case MP_QSTR_country: {
                int country =  -1;

                if(0x00 != netmgmt_wlan_ap_get_country(&country)) {
                    mp_printf(&mp_plat_print, "run get ap country failed.\n");
                }
                return MP_OBJ_NEW_SMALL_INT(country);
            } break;
        }
    } else {
        mp_map_elem_t *ssid = mp_map_lookup(kw_args, MP_OBJ_NEW_QSTR(MP_QSTR_ssid), MP_MAP_LOOKUP); // same in network_rt_wlan_connect
        mp_map_elem_t *key = mp_map_lookup(kw_args, MP_OBJ_NEW_QSTR(MP_QSTR_key), MP_MAP_LOOKUP);   // same in network_rt_wlan_connect
        mp_map_elem_t *info = mp_map_lookup(kw_args, MP_OBJ_NEW_QSTR(MP_QSTR_info), MP_MAP_LOOKUP); // same in network_rt_wlan_connect

        if((NULL != key) && ((NULL != ssid) || (NULL != info))) {
            // Call connect to set WiFi access point.
            return network_rt_wlan_connect(n_args, pos_args, kw_args);
        }

        enum { ARG_country };
        static const mp_arg_t allowed_args[] = {
            { MP_QSTR_country,                  MP_ARG_INT, {.u_int = -1} },
        };
        mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
        mp_arg_parse_all(n_args - 1, pos_args + 1, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

        if((-1) != args[ARG_country].u_int) {
            int country = args[ARG_country].u_int;

            if(0x00 != netmgmt_wlan_ap_set_country(country)) {
                mp_printf(&mp_plat_print, "run set ap country failed.\n");
                return mp_const_false;
            }
        }
    }

    return mp_const_true;
}

STATIC mp_obj_t network_rt_wlan_config(size_t n_args, const mp_obj_t *args, mp_map_t *kwargs) {
    py_rt_net_obj_t *self = MP_OBJ_TO_PTR(args[0]);

    if(MOD_NETWORK_STA_IF == self->itf) {
        return _network_rt_wlan_sta_config(n_args, args, kwargs);
    }
    return _network_rt_wlan_ap_config(n_args, args, kwargs);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_KW(network_rt_wlan_config_obj, 1, network_rt_wlan_config);

STATIC mp_obj_t _network_rt_wlan_get_sta_status(size_t n_args, const mp_obj_t *args) {
    py_rt_net_obj_t *self = MP_OBJ_TO_PTR(args[0]);

    if(0x01 == n_args) {
        return network_rt_wlan_isconnected(MP_OBJ_FROM_PTR(self));
    }

    switch (mp_obj_str_get_qstr(args[1])) {
        case MP_QSTR_rssi: {
            int rssi = -99;

            if(0x00 != netmgmt_wlan_sta_get_rssi(&rssi)) {
                rssi = -99;
                mp_printf(&mp_plat_print, "run sta get rssi failed.\n");
            }
            return MP_OBJ_NEW_SMALL_INT(rssi);
        } break;
        case MP_QSTR_ap: {
            struct rt_wlan_info_t info;

            if(0x00 != netmgmt_wlan_sta_get_ap_info(&info)) {
                mp_printf(&mp_plat_print, "run get ap info failed.\n");
                return mp_const_none;
            }

            return py_rt_wlan_info_from_struct(&info);
        } break;
    }

    mp_raise_ValueError(MP_ERROR_TEXT("unknown status param"));
}

STATIC mp_obj_t _network_rt_wlan_get_ap_status(size_t n_args, const mp_obj_t *args) {
    if(0x01 == n_args) {
        // check is actived
        int active = 0;

        if(0x00 != netmgmt_wlan_ap_isactived(&active)) {
            mp_printf(&mp_plat_print, "run ap isactive failed.\n");
            return mp_const_false;
        }
        return mp_obj_new_bool(active);
    }

    switch (mp_obj_str_get_qstr(args[1])) {
        case MP_QSTR_stations: {
            int sta_num = 0;
            struct rt_wlan_info_t sta_infos[RT_WLAN_STA_SCAN_MAX_AP];

            if(0x00 != netmgmt_wlan_ap_get_sta_info(&sta_num, sta_infos)) {
                mp_printf(&mp_plat_print, "run ap get connected station info failed.\n");
                return mp_const_none;
            }

            mp_obj_t station_list = mp_obj_new_list(0, NULL);

            for(int32_t i = 0; i < sta_num; i++) {
                struct rt_wlan_info_t *info = &sta_infos[i];
                mp_obj_t bssid = mp_obj_new_bytes(info->bssid, RT_WLAN_BSSID_MAX_LENGTH);
                mp_obj_list_append(station_list, bssid);
            }

            return station_list;
        } break;
    }

    mp_raise_ValueError(MP_ERROR_TEXT("unknown status param"));
}

STATIC mp_obj_t network_rt_wlan_status(size_t n_args, const mp_obj_t *args) {
    py_rt_net_obj_t *self = MP_OBJ_TO_PTR(args[0]);

    if(MOD_NETWORK_STA_IF == self->itf) {
        return _network_rt_wlan_get_sta_status(n_args, args);
    }
    return _network_rt_wlan_get_ap_status(n_args, args);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(network_rt_wlan_status_obj, 1, 2, network_rt_wlan_status);

STATIC mp_obj_t network_rt_wlan_stop(mp_obj_t self_in) {
    py_rt_net_obj_t *self = MP_OBJ_TO_PTR(self_in);

    if(MOD_NETWORK_AP_IF != self->itf) {
        mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("sta mode not support stop"));
    }

    if(0x00 != netmgmt_wlan_ap_stop()) {
        mp_printf(&mp_plat_print, "run stop failed.\n");
        return mp_const_false;
    }

    return mp_const_true;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_1(network_rt_wlan_stop_obj, network_rt_wlan_stop);
/* Constants *****************************************************************/
STATIC const mp_rom_map_elem_t rt_wlan_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR_active),              MP_ROM_PTR(&network_rt_net_active_obj) },
// { MP_ROM_QSTR(MP_QSTR_scan),                    MP_ROM_PTR(&network_rt_wlan_scan_obj) },             // only for sta
// { MP_ROM_QSTR(MP_QSTR_connect),                 MP_ROM_PTR(&network_rt_wlan_connect_obj) },          // only for sta
    { MP_ROM_QSTR(MP_QSTR_disconnect),              MP_ROM_PTR(&network_rt_wlan_disconnect_obj) },
// { MP_ROM_QSTR(MP_QSTR_isconnected),             MP_ROM_PTR(&network_rt_wlan_isconnected_obj) },      // only for sta
    { MP_ROM_QSTR(MP_QSTR_ifconfig),                MP_ROM_PTR(&network_rt_net_ifconfig_obj) },
    { MP_ROM_QSTR(MP_QSTR_config),                  MP_ROM_PTR(&network_rt_wlan_config_obj) },
    { MP_ROM_QSTR(MP_QSTR_status),                  MP_ROM_PTR(&network_rt_wlan_status_obj) },
// { MP_ROM_QSTR(MP_QSTR_stop),                    MP_ROM_PTR(&network_rt_wlan_stop_obj) },             // only for ap
// { MP_ROM_QSTR(MP_QSTR_info),                    MP_ROM_PTR(&py_rt_wlan_info_type) },                 // only for ap

    // security
    { MP_ROM_QSTR(MP_QSTR_SECURITY_OPEN),           MP_ROM_INT(SECURITY_OPEN) },
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WEP_PSK),        MP_ROM_INT(SECURITY_WEP_PSK) },
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WEP_SHARED),     MP_ROM_INT(SECURITY_WEP_SHARED) },
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WPA_TKIP_PSK),   MP_ROM_INT(SECURITY_WPA_TKIP_PSK) },
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WPA_TKIP_8021X), MP_ROM_INT(SECURITY_WPA_TKIP_8021X) },
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WPA_AES_PSK),    MP_ROM_INT(SECURITY_WPA_AES_PSK) },
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WPA_AES_8021X),  MP_ROM_INT(SECURITY_WPA_AES_8021X) },
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WPA2_AES_PSK),   MP_ROM_INT(SECURITY_WPA2_AES_PSK) },
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WPA2_AES_8021X), MP_ROM_INT(SECURITY_WPA2_AES_8021X) },
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WPA2_TKIP_PSK),  MP_ROM_INT(SECURITY_WPA2_TKIP_PSK) },
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WPA2_TKIP_8021X), MP_ROM_INT(SECURITY_WPA2_TKIP_8021X) },
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WPA2_MIXED_PSK), MP_ROM_INT(SECURITY_WPA2_MIXED_PSK) },
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WPA_WPA2_MIXED_PSK), MP_ROM_INT(SECURITY_WPA_WPA2_MIXED_PSK) },
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WPA_WPA2_MIXED_8021X), MP_ROM_INT(SECURITY_WPA_WPA2_MIXED_8021X) },
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WPA2_AES_CMAC),  MP_ROM_INT(SECURITY_WPA2_AES_CMAC) },
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WPS_OPEN),       MP_ROM_INT(SECURITY_WPS_OPEN) },
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WPS_SECURE),     MP_ROM_INT(SECURITY_WPS_SECURE) },
	{ MP_ROM_QSTR(MP_QSTR_SECURITY_WPA3_AES_PSK),   MP_ROM_INT(SECURITY_WPA3_AES_PSK) },
    { MP_ROM_QSTR(MP_QSTR_SECURITY_UNKNOWN),        MP_ROM_INT(SECURITY_UNKNOWN) },

    // bandrate
    { MP_ROM_QSTR(MP_QSTR_BAND_5GHZ),               MP_ROM_INT(RT_802_11_BAND_5GHZ) },
    { MP_ROM_QSTR(MP_QSTR_BAND_2_4GHZ),             MP_ROM_INT(RT_802_11_BAND_2_4GHZ) },
};

const mp_obj_type_t network_type_wlan_sta, network_type_wlan_ap;

STATIC py_rt_net_obj_t network_rt_wlan_sta = {{(mp_obj_type_t *)&network_type_wlan_sta}, MOD_NETWORK_STA_IF};
STATIC py_rt_net_obj_t network_rt_wlan_ap = {{(mp_obj_type_t *)&network_type_wlan_ap}, MOD_NETWORK_AP_IF};

STATIC mp_obj_t py_rt_wlan_type_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *all_args) {
    mp_obj_t rt_net_obj;

    if(type == &network_type_wlan_sta) {
        rt_net_obj = MP_OBJ_FROM_PTR(&network_rt_wlan_sta);
    } else {
        rt_net_obj = MP_OBJ_FROM_PTR(&network_rt_wlan_ap);
    }

    // Register with network module
    mod_network_register_nic(rt_net_obj);

    return rt_net_obj;
}

STATIC int network_type_sta_init_flag = 0;

STATIC mp_map_elem_t network_type_sta_locals_dict_table[MP_ARRAY_SIZE(rt_wlan_locals_dict_table) + 3];
STATIC MP_DEFINE_CONST_DICT_WITH_SIZE(network_type_sta_locals_dict, network_type_sta_locals_dict_table, MP_ARRAY_SIZE(rt_wlan_locals_dict_table) + 3);

MP_DEFINE_CONST_OBJ_TYPE(
    network_type_wlan_sta,
    MP_QSTR_rt_wlan_sta,
    MP_TYPE_FLAG_NONE,
    make_new, py_rt_wlan_type_make_new,
    locals_dict, &network_type_sta_locals_dict,
    protocol, &mod_network_nic_protocol_rtt_posix
);

STATIC int network_type_ap_init_flag = 0;

STATIC mp_map_elem_t network_type_ap_locals_dict_table[MP_ARRAY_SIZE(rt_wlan_locals_dict_table) + 2];
STATIC MP_DEFINE_CONST_DICT_WITH_SIZE(network_type_ap_locals_dict, network_type_ap_locals_dict_table, MP_ARRAY_SIZE(rt_wlan_locals_dict_table) + 2);

MP_DEFINE_CONST_OBJ_TYPE(
    network_type_wlan_ap,
    MP_QSTR_rt_wlan_ap,
    MP_TYPE_FLAG_NONE,
    make_new, py_rt_wlan_type_make_new,
    locals_dict, &network_type_ap_locals_dict,
    protocol, &mod_network_nic_protocol_rtt_posix
);

STATIC mp_obj_t network_wlan_make_new(size_t n_args, const mp_obj_t *args)
{
    int itf = MOD_NETWORK_STA_IF;

    if(0x01 == n_args) {
        itf = mp_obj_get_int(args[0]);
    }

    if(MOD_NETWORK_STA_IF == itf) {
        if(0x00 == network_type_sta_init_flag) {
            network_type_sta_init_flag = 1;

            const mp_map_elem_t *base_dict_map = (const mp_map_elem_t *)&rt_wlan_locals_dict_table;
            mp_map_elem_t *sta_dict_map = (mp_map_elem_t *)&network_type_sta_locals_dict_table;
            memcpy(sta_dict_map, base_dict_map, MP_ARRAY_SIZE(rt_wlan_locals_dict_table) * sizeof(mp_map_elem_t));

            network_type_sta_locals_dict_table[MP_ARRAY_SIZE(rt_wlan_locals_dict_table) + 0] = \
                (mp_map_elem_t){ MP_ROM_QSTR(MP_QSTR_scan), MP_OBJ_FROM_PTR(&network_rt_wlan_scan_obj) };
            network_type_sta_locals_dict_table[MP_ARRAY_SIZE(rt_wlan_locals_dict_table) + 1] = \
                (mp_map_elem_t){ MP_ROM_QSTR(MP_QSTR_connect), MP_OBJ_FROM_PTR(&network_rt_wlan_connect_obj) };
            network_type_sta_locals_dict_table[MP_ARRAY_SIZE(rt_wlan_locals_dict_table) + 2] = \
                (mp_map_elem_t){ MP_ROM_QSTR(MP_QSTR_isconnected), MP_OBJ_FROM_PTR(&network_rt_wlan_isconnected_obj) };
        }

        return MP_OBJ_TYPE_GET_SLOT(&network_type_wlan_sta, make_new)(&network_type_wlan_sta, 0, 0, MP_OBJ_NULL);
    } else {
        if(0x00 == network_type_ap_init_flag) {
            network_type_ap_init_flag = 1;

            const mp_map_elem_t *base_dict_map = (const mp_map_elem_t *)&rt_wlan_locals_dict_table;
            mp_map_elem_t *ap_dict_map = (mp_map_elem_t *)&network_type_ap_locals_dict_table;
            memcpy(ap_dict_map, base_dict_map, MP_ARRAY_SIZE(rt_wlan_locals_dict_table) * sizeof(mp_map_elem_t));

            network_type_ap_locals_dict_table[MP_ARRAY_SIZE(rt_wlan_locals_dict_table) + 0] = \
                (mp_map_elem_t){ MP_ROM_QSTR(MP_QSTR_stop), MP_OBJ_FROM_PTR(&network_rt_wlan_stop_obj) };
            network_type_ap_locals_dict_table[MP_ARRAY_SIZE(rt_wlan_locals_dict_table) + 1] = \
                (mp_map_elem_t){ MP_ROM_QSTR(MP_QSTR_info), MP_OBJ_FROM_PTR(&network_rt_wlan_ap_get_info_obj) };
        }

        return MP_OBJ_TYPE_GET_SLOT(&network_type_wlan_ap, make_new)(&network_type_wlan_ap, 0, 0, MP_OBJ_NULL);
    }
}
MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(network_wlan_make_new_obj, 0, 1, network_wlan_make_new);

#endif // CONFIG_ENABLE_NETWORK_RT_WLAN

void network_rt_wlan_deinit(void)
{
#ifdef CONFIG_ENABLE_NETWORK_RT_WLAN
    network_type_sta_init_flag = 0;
    network_type_ap_init_flag = 0;
#endif // CONFIG_ENABLE_NETWORK_RT_WLAN
}

STATIC mp_obj_t network_rt_set_dft_dev(mp_obj_t name)
{
    const char* dev_name = mp_obj_str_get_str(name);
    int         name_len = strlen(dev_name);

    if ((0x00 >= name_len) || (32 <= name_len)) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid device name"));
    }

    if(0x00 != netmgmt_utils_set_defeault_dev((char *)dev_name)) {
        mp_printf(&mp_plat_print, "run set default netdev failed.\n");
        return mp_const_false;
    }

    return mp_const_true;
}
MP_DEFINE_CONST_FUN_OBJ_1(network_rt_set_dft_dev_obj, network_rt_set_dft_dev);

STATIC mp_obj_t network_rt_get_dft_dev(void)
{
    char dev_name[32];

    if(0x00 != netmgmt_utils_get_defeault_dev(dev_name)) {
        mp_printf(&mp_plat_print, "run get default netdev failed.\n");
        return mp_const_none;
    }

    return mp_obj_new_str_via_qstr(dev_name, strlen(dev_name));
}
MP_DEFINE_CONST_FUN_OBJ_0(network_rt_get_dft_dev_obj, network_rt_get_dft_dev);

STATIC mp_obj_t network_rt_get_dev_list(void)
{
    int dev_num = 0;
    char names[NET_DEV_MAX_CNT][32];

    mp_obj_t dev_list;

    if(0x00 != netmgmt_utils_get_dev_list(&dev_num, names)) {
        mp_printf(&mp_plat_print, "run get netdev list failed.\n");
        return mp_const_none;
    }

    dev_list = mp_obj_new_list(0, NULL);
    for (int i = 0; i < dev_num; i++) {
        mp_obj_t name_obj = mp_obj_new_str_via_qstr(names[i], strlen(names[i]));
        mp_obj_list_append(dev_list, name_obj);
    }

    return dev_list;
}
MP_DEFINE_CONST_FUN_OBJ_0(network_rt_get_dev_list_obj, network_rt_get_dev_list);

#endif // MICROPY_PY_NETWORK
