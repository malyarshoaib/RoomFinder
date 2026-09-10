package com.campus.roomfinder.controller;

import com.campus.roomfinder.repository.CourseScheduleRepository;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.*;

import java.time.LocalTime;
import java.util.ArrayList;
import java.util.List;
@CrossOrigin(origins = "*")
@RestController
@RequestMapping("/api/rooms")
public class RoomController {
    private final CourseScheduleRepository repository;

    // 2. Create a constructor so Spring Boot can inject the repository
    public RoomController(CourseScheduleRepository repository) {
        this.repository = repository;
    }
    @GetMapping("/empty")
    public List<EmptyRoomResponse> getEmptyRooms(
            @RequestParam char day,
            @RequestParam
            @DateTimeFormat(iso = DateTimeFormat.ISO.TIME)
            LocalTime time) {

        List<Object[]> rawRooms = repository.findEmptyRooms(day, time);

        List<EmptyRoomResponse> formattedRooms = new ArrayList<>();

        for (int i = 0; i < rawRooms.size(); i ++){
            Object[] row = rawRooms.get(i);
            String building = (String) row[0];
            String room = (String) row[1];
            formattedRooms.add(new EmptyRoomResponse(building, room));
        }

        return formattedRooms;
    }

}
