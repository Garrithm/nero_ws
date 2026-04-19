#pragma once

#ifdef WIN32
#define EXPORT_API __declspec(dllexport)
#else
#define EXPORT_API __attribute__((visibility("default")))
#endif

#include <string>
#include "types.hpp"
typedef void(*pareCallback)(bool result, const int& type);
extern "C"
{
    EXPORT_API bool xv_device_init_only_wireless_controller(const char* COM);
    EXPORT_API bool xv_start_wireless_controller();
    EXPORT_API bool xv_stop_wireless_controller();
    // wireless controller 
    EXPORT_API bool xv_wireless_controller_get_6dof(Vector3 *position, Vector4 *quaternion, WirelessControllerKeys* keys, int type);
    EXPORT_API void xv_wireless_controller_get_device_info(WirelessControllerDeviceInfo* info, int type);
    //time unit is milliseconds, enable == true start enable == false stop
    EXPORT_API void xv_wireless_controller_control_vibration(int time, bool enable, int type);
    EXPORT_API void xv_wireless_controller_pair(pareCallback resultCallback, int type);
    EXPORT_API bool xv_wireless_controller_get_apriltag(int type, TagData* tag);
    EXPORT_API void xv_wireless_controller_start_apriltag(int type, double size);
    EXPORT_API void xv_wireless_controller_stop_apriltag(int type);
}

