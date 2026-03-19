#include "sim/network_accel/WorkerPool.hh"

#include <algorithm>

#include "base/logging.hh"
#include "sim/network_accel/DeterministicMerge.hh"

namespace gem5
{

WorkerPool::WorkerPool(uint32_t requested_workers, uint32_t partitions)
    : _requestedWorkers(requested_workers),
      _workerCount(std::min(requested_workers, partitions)),
      _partitionCount(partitions)
{
    panic_if(
        requested_workers == 0,
        "Parallel network acceleration requires at least one requested worker"
    );
    panic_if(
        partitions == 0,
        "Parallel network acceleration requires at least one partition"
    );

    for (uint32_t queue = 1; queue <= _workerCount; ++queue) {
        _queueIds.push_back(queue);
    }
}

uint32_t
WorkerPool::requestedWorkers() const
{
    return _requestedWorkers;
}

uint32_t
WorkerPool::workerCount() const
{
    return _workerCount;
}

uint32_t
WorkerPool::partitionCount() const
{
    return _partitionCount;
}

uint32_t
WorkerPool::queueForPartition(uint32_t partition) const
{
    panic_if(
        _queueIds.empty(),
        "Parallel network acceleration has no queue assignments"
    );
    return _queueIds.at(partition % _queueIds.size());
}

const std::vector<uint32_t> &
WorkerPool::queueIds() const
{
    return _queueIds;
}

std::string
WorkerPool::queueSummary() const
{
    return deterministicMergeUintList(_queueIds);
}

} // namespace gem5
