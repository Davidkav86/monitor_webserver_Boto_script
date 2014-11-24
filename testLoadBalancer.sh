#!/bin/bash

url="http://dk-loadbalancer-355490230.eu-west-1.elb.amazonaws.com"

i=0

while [ $i -le 2000 ] 

do
  curl "$url/$i"
  i=$(( $i + 1 ))
done
