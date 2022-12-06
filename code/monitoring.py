import json
import psutil
import os
import sys
import argparse
import time
import threading
import logging
# 根据自己的文件名及函数名导入主函数
from inference import main


def get_cpu_frequency():
    cpu_frequency = {}
    try:
        cpu_frequency_all = psutil.cpu_freq()
        cpu_frequency['current'] = cpu_frequency_all.current
        cpu_frequency['min'] = cpu_frequency_all.min
        cpu_frequency['max'] = cpu_frequency_all.max
    except:
        return cpu_frequency

    return cpu_frequency


def get_cpu_time():
    cpu_time = {}
    cpu_time_all = psutil.cpu_times()
    cpu_time['user'] = cpu_time_all.user
    cpu_time['nice'] = cpu_time_all.nice
    cpu_time['system'] = cpu_time_all.system
    cpu_time['idle'] = cpu_time_all.idle
    cpu_time['iowait'] = cpu_time_all.iowait
    cpu_time['irq'] = cpu_time_all.irq
    cpu_time['softirq'] = cpu_time_all.softirq
    cpu_time['steal'] = cpu_time_all.steal
    cpu_time['guest'] = cpu_time_all.guest
    cpu_time['guest_nice'] = cpu_time_all.guest_nice

    return cpu_time


def get_all_disk_info():
    disk_all = []
    for num, device in enumerate(psutil.disk_partitions()):
        dic_disk_all = {}
        dic_disk_all['id'] = num
        dic_disk_all['device'] = device.device
        dic_disk_all['mountpoint'] = device.mountpoint
        dic_disk_all['fstype'] = device.fstype
        dic_disk_all['opts'] = device.opts
        dic_disk_all['maxfile'] = device.maxfile
        dic_disk_all['maxpath'] = device.maxpath
        disk_all.append(dic_disk_all)

    return disk_all


def get_disk_used():
    disk_used = {}
    disk_used_all = psutil.disk_usage('/')
    disk_used['total'] = disk_used_all.total
    disk_used['used'] = disk_used_all.used
    disk_used['free'] = disk_used_all.free
    disk_used['percent'] = disk_used_all.percent

    return disk_used


def get_disk_io():
    disk_io = {}
    disk_io_all = psutil.disk_io_counters()
    disk_io['read_count'] = disk_io_all.read_count
    disk_io['write_count'] = disk_io_all.write_count
    disk_io['read_bytes'] = disk_io_all.read_bytes
    disk_io['write_bytes'] = disk_io_all.write_bytes
    disk_io['read_time'] = disk_io_all.read_time
    disk_io['write_time'] = disk_io_all.write_time
    disk_io['read_merged_count'] = disk_io_all.read_merged_count
    disk_io['write_merged_count'] = disk_io_all.write_merged_count
    disk_io['busy_time'] = disk_io_all.busy_time

    return disk_io


def get_storage_info():
    storage = {}
    storage_all = psutil.swap_memory()
    storage['total'] = storage_all.total
    storage['used'] = storage_all.used
    storage['free'] = storage_all.free
    storage['percent'] = storage_all.percent
    storage['sin'] = storage_all.sin
    storage['sout'] = storage_all.sout

    return storage


def get_process_top3():
    process_top3 = []
    config = ['pid', 'name', 'status', 'create_time', 'memory_percent', 'io_counters', 'num_threads']
    for i, device in enumerate(psutil.process_iter(config)):
        process = {}

        device = device.info
        io_counters = device['io_counters']
        dic_io = {}
        if io_counters is not None:
            dic_io['read_count'] = io_counters.read_count
            dic_io['write_count'] = io_counters.write_count
            dic_io['read_bytes'] = io_counters.read_bytes
            dic_io['write_bytes'] = io_counters.write_bytes
            dic_io['read_chars'] = io_counters.read_chars
            dic_io['write_chars'] = io_counters.write_chars

        process['id'] = i
        process['pid'] = device['pid']
        process['name'] = device['name']
        process['status'] = device['status']
        process['create_time'] = device['create_time']
        process['memory_percent'] = round(device['memory_percent'], 2)  # 进程内存利用率
        process['io_counters'] = dic_io  # 进程的IO信息,包括读写IO数字及参数
        process['num_threads'] = device['num_threads']   # 进程开启的线程数
        process_top3.append(process)
        if i > 2:
            break

    return process_top3


def get_net_info():
    net = {}
    net_all = psutil.net_io_counters()
    net['bytes_sent'] = net_all.bytes_sent
    net['bytes_recv'] = net_all.bytes_recv
    net['packets_sent'] = net_all.packets_sent
    net['packets_recv'] = net_all.packets_recv
    net['errin'] = net_all.errin
    net['errout'] = net_all.errout
    net['dropin'] = net_all.dropin
    net['dropout'] = net_all.dropout

    return net


def read_byte(result_evaluate):
    # 计算磁盘写入字节数
    def is_Chinese(word):
        for ch in word:
            if '\u4e00' <= ch <= '\u9fff':
                return True
        return False
    result_evaluate = json.dumps(result_evaluate, indent=4, ensure_ascii=False)
    byte_num = 0
    for i in result_evaluate:
        if is_Chinese(i):
                byte_num += 3
        else:
                byte_num += 1

    return byte_num


def CPU_Memory_utilization():
    # global cpu_utilization_list, memory_utilization_list
    # cpu_utilization_list = []
    # memory_utilization_list = []

    while True:
        cul_lis = psutil.cpu_percent(interval=1, percpu=True)
        cul = sum(cul_lis) / len(cul_lis)
        # cpu_utilization_list.append(cul)
        # memory_utilization_list.append(psutil.virtual_memory().percent)

        logging.info("CPU占用率:" + str(cul))
        storage = get_storage_info()
        storage['内存占用率'] = psutil.virtual_memory().percent
        logging.info("内存信息:" + str(storage))

        time.sleep(10)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='')
    parser.add_argument('--input', default='/input', help='Location of WIDERFACE root directory')
    parser.add_argument('--result', default='/result', help='Location of WIDERFACE root directory')
    # parser.add_argument('--logfile', default='/logfile', help='Monitor the log output path')
    parser.add_argument('--mon', default='no', help='Whether to start the monitoring tool')
    args = parser.parse_args()
    while len(sys.argv) > 1:
        sys.argv.pop()
    input_path = args.input
    result_path = args.result
    log_path = ""
    # log_path = os.path.join(args.logfile, 'info.log')

    read_flie_size = 0
    for root, dirs, files in os.walk(input_path, topdown=True):
        for file in files:
            txtfile = os.path.join(root, file)
            jsonfile = os.path.join(root.replace(input_path, result_path), file.replace(".txt", ".json"))
            log_path = os.path.join(root.replace(input_path, result_path), "log")
            if not os.path.exists(log_path) and args.mon != 'no':
                os.makedirs(log_path)
            log_path = os.path.join(log_path,  "info.log")
            read_flie_size += os.path.getsize(txtfile)

    # 是否启动资源评测工具进行监控，默认不启动，启动时传参mon=yes(不为no都可以)
    if args.mon == 'no':
        len_data, test_time, df = main(input_path, result_path)
    else:
        log = logging.getLogger()
        log.setLevel("INFO")
        file = logging.FileHandler(log_path, encoding="utf-8")
        fmt = '%(asctime)s--%(levelname)s-%(filename)s-%(lineno)d >>> %(message)s'
        pycharm_fmt = logging.Formatter(fmt=fmt)
        file.setFormatter(fmt=pycharm_fmt)
        log.addHandler(file)

        th = threading.Thread(target=CPU_Memory_utilization)
        th.setDaemon(True)  # 将子线程设置为守护线程（当主线程执行完成后，子线程无论是否执行完成都停止执行）
        th.start()

        time.sleep(1)
        len_data, test_time, df = main(input_path, result_path)
        write_flie_size = read_byte(df)

        # 吞吐量及响应时间
        handling_capacity = {"handling_capacity(t/s)":round(len_data / test_time, 2),
                        "numerator_test_len":len_data,
                        "denominator_predict_time(s)":round(test_time, 2)}
        response_time = {"response_time(ms/t)":round(test_time / len_data * 1000 , 2),
                        "numerator_predict_time(s)":round(test_time, 2),
                        "denominator_test_len":len_data}


        cpu_ = {"逻辑CPU个数":psutil.cpu_count(),
                "物理CPU个数":psutil.cpu_count(logical=False),
                "CPU频率":get_cpu_frequency(),
                "CPU时间花费":get_cpu_time()}

        disk_ = {"程序读取字节数": read_flie_size,
                 "程序写入字节数": write_flie_size,
                 "所有已挂磁盘":get_all_disk_info(),
                 "磁盘使用情况":get_disk_used(),
                 "磁盘io统计":get_disk_io()}

        course_ = {"运行中进程top3":get_process_top3(),
                   "运行中全部进程":psutil.pids(),
                   "开机时间":psutil.boot_time()}

        logging.info("吞吐量:" + str(handling_capacity))
        logging.info("响应时间:" + str(response_time))
        logging.info("模型io字节及磁盘信息:" + str(disk_))
        logging.info("CPU信息:" + str(cpu_))
        logging.info("网卡信息:" + str(get_net_info()))
        logging.info("进程信息:" + str(course_))


