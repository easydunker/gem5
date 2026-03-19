#ifndef __SIM_NETWORK_ACCEL_NETWORK_ACCEL_COORDINATOR_HH__
#define __SIM_NETWORK_ACCEL_NETWORK_ACCEL_COORDINATOR_HH__

#include <memory>
#include <string>

#include "sim/network_accel/NetworkAccelConfig.hh"

namespace gem5
{

class Event;
class EventQueue;
class WorkerPool;

class NetworkAccelCoordinator
{
  public:
    static NetworkAccelCoordinator &instance();

    void configure(const NetworkAccelConfig &config);
    void configure(const std::string &mode, uint32_t workers);
    void activateParallelMode(uint32_t partitions);
    void reset();

    const NetworkAccelConfig &config() const;
    NetworkAccelMode mode() const;
    uint32_t workers() const;
    std::string modeName() const;
    NetworkAccelMode requestedMode() const;
    uint32_t requestedWorkers() const;
    std::string requestedModeName() const;
    bool downgraded() const;
    const std::string &note() const;
    uint32_t parallelPartitions() const;
    std::string queueSummary() const;
    bool serialBatchingEnabled() const;
    uint32_t dispatchBatchLimit() const;

    void beforeSimulation();
    void afterSimulation();
    void onLoopEnter(EventQueue *eventq, bool main_queue);
    void beforeDispatch(EventQueue *eventq);
    void afterDispatch(EventQueue *eventq, Event *exit_event);

  private:
    NetworkAccelCoordinator() = default;

    NetworkAccelConfig _requestedConfig;
    NetworkAccelConfig _config;
    std::string _note;
    uint32_t _parallelPartitions = 0;
    std::unique_ptr<WorkerPool> _workerPool;
};

} // namespace gem5

#endif // __SIM_NETWORK_ACCEL_NETWORK_ACCEL_COORDINATOR_HH__
