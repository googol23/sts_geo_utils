// Default output: data/output/sensors.csv relative to the working directory.
#include <TClass.h>
#include <TFile.h>
#include <TGeoBBox.h>
#include <TGeoManager.h>
#include <TGeoMatrix.h>
#include <TGeoNode.h>
#include <TGeoVolume.h>
#include <TKey.h>
#include <TString.h>
#include <TSystem.h>

#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <string>

namespace sts_inspector
{
  std::string quote(const std::string& value)
  {
    std::string result = "\"";
    for (char c : value)
      result += (c == '"' ? "\"\"" : std::string(1, c));
    return result + "\"";
  }

  void walk(TGeoVolume* volume, const TGeoHMatrix& global, const std::string& path, std::ostream& output,
            unsigned& count, std::ostream* nodeOutput = nullptr)
  {
    if (nodeOutput) {
      // Node frames use the node origin, not the shape's bounding-box origin.
      const double origin[3] = {0., 0., 0.};
      double translation[3];
      global.LocalToMaster(origin, translation);
      *nodeOutput << quote(path);
      for (double v : translation)
        *nodeOutput << ',' << v;
      const double* rotation = global.GetRotationMatrix();
      for (int i = 0; i < 9; ++i)
        *nodeOutput << ',' << rotation[i];
      *nodeOutput << '\n';
    }
    static const std::regex sensorPattern("Sensor[0-9]+");
    if (std::regex_match(volume->GetName(), sensorPattern)) {
      auto* box = dynamic_cast<TGeoBBox*>(volume->GetShape());
      if (!box || volume->GetShape()->IsA() != TGeoBBox::Class())
        throw std::runtime_error("Expected a box sensor at " + path);
      double center[3];
      global.LocalToMaster(box->GetOrigin(), center);
      output << quote(path);
      for (double v : center)
        output << ',' << v;
      // Full dimensions in the sensor's own axes; ROOT getters are half lengths.
      output << ',' << 2 * box->GetDX() << ',' << 2 * box->GetDY() << ',' << 2 * box->GetDZ();
      const double* rotation = global.GetRotationMatrix();
      for (int i = 0; i < 9; ++i)
        output << ',' << rotation[i];
      output << '\n';
      ++count;
    }
    for (int i = 0; i < volume->GetNdaughters(); ++i) {
      auto* child = volume->GetNode(i);
      TGeoHMatrix transform(global);
      transform.Multiply(child->GetMatrix());
      walk(child->GetVolume(), transform, path + "/" + child->GetName(), output, count, nodeOutput);
    }
  }

  void extract(const char* input, const char* output, const char* nodeOutput = "")
  {
    if (std::string(input) == output) throw std::runtime_error("Input and output must differ");
    const bool writeNodes = nodeOutput && nodeOutput[0];
    if (writeNodes && (std::string(input) == nodeOutput || std::string(output) == nodeOutput))
      throw std::runtime_error("Input, sensor output and node output must differ");
    std::unique_ptr<TFile> file(TFile::Open(input, "READ"));
    if (!file || file->IsZombie()) throw std::runtime_error("Cannot open geometry file");
    TGeoManager* manager  = nullptr;
    TGeoVolume* volume    = nullptr;
    TGeoMatrix* placement = nullptr;
    // Inspect classes first: do not deserialize both a manager and its exported volumes.
    TIter next(file->GetListOfKeys());
    while (auto* key = dynamic_cast<TKey*>(next())) {
      auto* cls = TClass::GetClass(key->GetClassName());
      if (cls && cls->InheritsFrom(TGeoManager::Class())) {
        if (manager) throw std::runtime_error("Multiple geometry managers in file");
        manager = dynamic_cast<TGeoManager*>(key->ReadObj());
      }
    }
    TGeoHMatrix transform;
    std::string path;
    if (manager) {
      auto* top = manager->GetTopNode();
      if (!top) throw std::runtime_error("Geometry has no top node");
      volume = top->GetVolume();
      transform.Multiply(top->GetMatrix());
      path = std::string("/") + top->GetName();
    }
    else {
      next.Reset();
      while (auto* key = dynamic_cast<TKey*>(next())) {
        auto* cls = TClass::GetClass(key->GetClassName());
        if (cls && cls->InheritsFrom(TGeoVolume::Class())) {
          if (volume) throw std::runtime_error("Multiple exported volumes in file");
          volume = dynamic_cast<TGeoVolume*>(key->ReadObj());
        }
        else if (cls && cls->InheritsFrom(TGeoMatrix::Class())) {
          if (placement) throw std::runtime_error("Multiple placement matrices in file");
          placement = dynamic_cast<TGeoMatrix*>(key->ReadObj());
        }
      }
      if (!volume) throw std::runtime_error("No TGeoManager or TGeoVolume found");
      if (!placement) throw std::runtime_error("Volume export has no global placement matrix");
      transform.Multiply(placement);
      // Exported volumes have no top node. This is a volume-rooted debug path.
      path = std::string("/") + volume->GetName();
    }
    std::ostringstream rows;
    rows << std::setprecision(17);
    std::ostringstream nodeRows;
    nodeRows << std::setprecision(17);
    unsigned count = 0;
    walk(volume, transform, path, rows, count, writeNodes ? &nodeRows : nullptr);
    if (!count) throw std::runtime_error("No SensorNN placements found");
    std::ofstream stream(output);
    if (!stream) throw std::runtime_error("Cannot open sensor CSV output");
    stream << "node_path,x,y,z,dx,dy,dz,r00,r01,r02,r10,r11,r12,r20,r21,r22\n" << rows.str();
    stream.close();
    if (!stream) throw std::runtime_error("Failed writing sensor CSV");
    if (writeNodes) {
      std::ofstream nodes(nodeOutput);
      if (!nodes) throw std::runtime_error("Cannot open node transform CSV output");
      nodes << "node_path,x,y,z,r00,r01,r02,r10,r11,r12,r20,r21,r22\n" << nodeRows.str();
      nodes.close();
      if (!nodes) throw std::runtime_error("Failed writing node transform CSV");
    }
    std::cout << "Extracted " << count << " sensor placements to " << output << '\n';
  }
}  // namespace sts_inspector

void extract_sts_sensors(const char* input, const char* output = "sensors.csv", const char* nodeOutput = "")
{
  try {
    TString destination(output);
    if (!destination.BeginsWith("/")) {
      destination = TString(gSystem->WorkingDirectory()) + "/data/output/" + destination;
    }
    TString parent = gSystem->DirName(destination.Data());
    if (gSystem->AccessPathName(parent.Data()) && gSystem->mkdir(parent.Data(), kTRUE) != 0)
      throw std::runtime_error("Cannot create output directory: " + std::string(parent.Data()));
    // The optional node-transform filename is explicit, relative to the cwd.
    sts_inspector::extract(input, destination.Data(), nodeOutput);
  }
  catch (const std::exception& error) {
    std::cerr << "extract_sts_sensors: " << error.what() << '\n';
    gSystem->Exit(1);
  }
}
