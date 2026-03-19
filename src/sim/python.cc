/*
 * Copyright 2019 Google, Inc.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are
 * met: redistributions of source code must retain the above copyright
 * notice, this list of conditions and the following disclaimer;
 * redistributions in binary form must reproduce the above copyright
 * notice, this list of conditions and the following disclaimer in the
 * documentation and/or other materials provided with the distribution;
 * neither the name of the copyright holders nor the names of its
 * contributors may be used to endorse or promote products derived from
 * this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 * "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
 * A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
 * OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
 * SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
 * LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 * DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
 * THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 * (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

#include "pybind11/pybind11.h"
#include "sim/init.hh"
#include "sim/network_accel/NetworkAccelCoordinator.hh"
#include "sim/port.hh"

namespace gem5
{

namespace
{

void
sim_pybind(pybind11::module_ &m_internal)
{
    pybind11::module_ m = m_internal.def_submodule("sim");
    pybind11::class_<
        Port, std::unique_ptr<Port, pybind11::nodelete>>(m, "Port")
        .def("bind", &Port::bind)
        .def("name", &Port::name)
        ;
    m.def(
        "configure_network_accel",
        [](const std::string &mode, uint32_t workers) {
            NetworkAccelCoordinator::instance().configure(mode, workers);
        }
    );
    m.def(
        "reset_network_accel",
        []() {
            NetworkAccelCoordinator::instance().reset();
        }
    );
    m.def(
        "get_network_accel_mode",
        []() {
            return NetworkAccelCoordinator::instance().modeName();
        }
    );
    m.def(
        "get_network_accel_workers",
        []() {
            return NetworkAccelCoordinator::instance().workers();
        }
    );
    m.def(
        "activate_parallel_network_accel",
        [](uint32_t partitions) {
            NetworkAccelCoordinator::instance().activateParallelMode(
                partitions
            );
        }
    );
    m.def(
        "get_network_accel_requested_mode",
        []() {
            return NetworkAccelCoordinator::instance().requestedModeName();
        }
    );
    m.def(
        "get_network_accel_requested_workers",
        []() {
            return NetworkAccelCoordinator::instance().requestedWorkers();
        }
    );
    m.def(
        "network_accel_downgraded",
        []() {
            return NetworkAccelCoordinator::instance().downgraded();
        }
    );
    m.def(
        "get_network_accel_note",
        []() {
            return NetworkAccelCoordinator::instance().note();
        }
    );
    m.def(
        "get_network_accel_parallel_partitions",
        []() {
            return NetworkAccelCoordinator::instance().parallelPartitions();
        }
    );
    m.def(
        "get_network_accel_queue_summary",
        []() {
            return NetworkAccelCoordinator::instance().queueSummary();
        }
    );
}
EmbeddedPyBind embed_("sim", &sim_pybind);

} // anonymous namespace
} // namespace gem5
