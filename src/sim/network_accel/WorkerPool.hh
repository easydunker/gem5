#ifndef __SIM_NETWORK_ACCEL_WORKER_POOL_HH__
#define __SIM_NETWORK_ACCEL_WORKER_POOL_HH__

#include <cstdint>
#include <string>
#include <vector>

namespace gem5
{

class WorkerPool
{
  public:
    WorkerPool(uint32_t requested_workers, uint32_t partitions);

    uint32_t requestedWorkers() const;
    uint32_t workerCount() const;
    uint32_t partitionCount() const;
    uint32_t queueForPartition(uint32_t partition) const;
    const std::vector<uint32_t> &queueIds() const;
    std::string queueSummary() const;

  private:
    uint32_t _requestedWorkers = 0;
    uint32_t _workerCount = 0;
    uint32_t _partitionCount = 0;
    std::vector<uint32_t> _queueIds;
};

} // namespace gem5

#endif // __SIM_NETWORK_ACCEL_WORKER_POOL_HH__
