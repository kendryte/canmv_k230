#ifndef QUANTIFIER_H
#define QUANTIFIER_H

#include "num.h"


// Build each pattern once on first use; share it across translation units.
inline const std::regex &RE_TEMPERATURE() {
    static const std::regex value(R"((-?)(\d+(\.\d+)?)(°|°C|℃|度|摄氏度))");
    return value;
}

std::string replace_temperature(std::smatch match);

#endif