#ifndef __SIM_NETWORK_ACCEL_DETERMINISTIC_MERGE_HH__
#define __SIM_NETWORK_ACCEL_DETERMINISTIC_MERGE_HH__

#include <algorithm>
#include <cstdint>
#include <sstream>
#include <string>
#include <vector>

namespace gem5
{

inline std::string
deterministicMergeUintList(const std::vector<uint32_t> &values)
{
    std::vector<uint32_t> merged(values);
    std::sort(merged.begin(), merged.end());
    merged.erase(std::unique(merged.begin(), merged.end()), merged.end());

    std::ostringstream out;
    for (size_t i = 0; i < merged.size(); ++i) {
        if (i != 0) {
            out << ",";
        }
        out << merged[i];
    }

    return out.str();
}

} // namespace gem5

#endif // __SIM_NETWORK_ACCEL_DETERMINISTIC_MERGE_HH__
