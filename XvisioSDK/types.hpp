#pragma once
struct Vector3
{
    float x;
    float y;
    float z;
};

struct Vector4
{
    float x;
    float y;
    float z;
    float w;
};

/**
 * @brief Rotation and translation structure
 */
struct transform
{
    double rotation[9];    //!< Rotation matrix (row major)
    double translation[3]; //!< Translation vector
};

struct TagData
{
    int tagID;
    Vector3 position;
    Vector4 quaternion;
    int confidence;
};


struct WirelessControllerKeys
{
    int keyTrigger;
    int keySide;
    int rocker_x;
    int rocker_y;
    int key;
};

struct WirelessControllerDeviceInfo
{
    int battery;
    int temp;
    int sleep;
    int charging;
    char sn[10];
};

enum WirelessControllerDeviceType
{
    UNKNOW = 0,
    LEFT = 0xC4,
    RIGHT = 0xC5,
    ALL = 0xC6
};
