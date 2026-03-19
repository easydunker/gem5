#ifndef __SIM_NETWORK_ACCEL_NETWORK_ACCEL_MODE_HH__
#define __SIM_NETWORK_ACCEL_NETWORK_ACCEL_MODE_HH__

#include <string>

namespace gem5
{

enum class NetworkAccelMode
{
    Off,
    SerialBatched,
    Parallel,
};

inline const char *
networkAccelModeToString(NetworkAccelMode mode)
{
    switch (mode) {
      case NetworkAccelMode::Off:
        return "off";
      case NetworkAccelMode::SerialBatched:
        return "serial_batched";
      case NetworkAccelMode::Parallel:
        return "parallel";
    }

    return "off";
}

NetworkAccelMode networkAccelModeFromString(const std::string &mode);

} // namespace gem5

#endif // __SIM_NETWORK_ACCEL_NETWORK_ACCEL_MODE_HH__
