#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <math.h>

#include "types.hpp"
#include "CInterfaces.h"

int main(int argc, char* argv[])
{

    if(!xv_start_wireless_controller())
    {
        printf("controller start FAIL!\n");
        return 0;
    }

    int time = 10;
    int loop = 0;
    if(argc > 1)
    {
        time = std::stoi(argv[1]);
    }
    while(true)
    {
        Vector3 position[2] = {0};
        Vector4 quat[2] = {0};
        WirelessControllerKeys keys[2] = {0};
        WirelessControllerDeviceInfo info[2] = {0};
        TagData tag[2];

        xv_wireless_controller_get_device_info(&info[1], 2);
        if(info[1].battery > 0)
        {
            printf("right[%s] battery:%d, temp:%d sleep:%d, charging:%d\n",
                info[1].sn, info[1].battery, info[1].temp, info[1].sleep, info[1].charging);
        }

        if(xv_wireless_controller_get_6dof(&position[1], &quat[1], &keys[1], 2))
        {
            printf("right position(%.3f, %.3f, %.3f) quaternion(%.3f, %.3f, %.3f, %.3f)\n",
                position[1].x, position[1].y, position[1].z, quat[1].x, quat[1].y, quat[1].z, quat[1].w);
            printf("key event key: %d, trigger: %d, side: %d, rockerx: %d, rockery: %d\n", keys[1].key, keys[1].keyTrigger, keys[1].keySide, keys[1].rocker_x, keys[1].rocker_y);
        }

        printf("[%d]===========\n", loop);
        loop++;
        usleep(1000*1000);
    }

    usleep(1000*1000);
    xv_stop_wireless_controller();
    printf("\n[exit]===========\n");
    return 0;
}