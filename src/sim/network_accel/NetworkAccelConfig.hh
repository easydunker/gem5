#ifndef __SIM_NETWORK_ACCEL_NETWORK_ACCEL_CONFIG_HH__
#define __SIM_NETWORK_ACCEL_NETWORK_ACCEL_CONFIG_HH__

#include <cstdint>
#include <string>

#include "sim/network_accel/NetworkAccelMode.hh"

namespace gem5
{

struct NetworkAccelConfig
{
    NetworkAccelMode mode = NetworkAccelMode::Off;
    uint32_t workers = 1;

    std::string
    modeName() const
    {
        return networkAccelModeToString(mode);
    }
};

} // namespace gem5

#endif // __SIM_NETWORK_ACCEL_NETWORK_ACCEL_CONFIG_HH__
