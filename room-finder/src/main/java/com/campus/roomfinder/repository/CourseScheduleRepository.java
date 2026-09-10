package com.campus.roomfinder.repository;

import com.campus.roomfinder.entity.CourseSchedule;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.stereotype.Repository;
import org.springframework.data.repository.query.Param;
import java.time.LocalTime;
import java.util.List;

@Repository

public interface CourseScheduleRepository extends JpaRepository<CourseSchedule, Long> {
    @Query(value = "SELECT DISTINCT building, room_number FROM course_schedules " +
            "EXCEPT " +
            "SELECT building, room_number FROM course_schedules " +
            "WHERE day_of_week = :targetDay " +
            "AND start_time <= :targetTime " +
            "AND end_time > :targetTime", nativeQuery = true)
    List<Object[]> findEmptyRooms(@Param("targetDay") char targetDay, @Param("targetTime") LocalTime targetTime);}